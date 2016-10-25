
import renpy.display
import pygame_sdl2 as pygame
import random
import ctypes

from OpenGL import GL as gl
import euclid
import math
import json

import shader
import shadercode
import mesh
import utils

class TextureEntry:
    def __init__(self, image, sampler):
        self.sampler = sampler

        if isinstance(image, (pygame.Surface)):
            self.image = None
            surface = image
        else:
            self.image = image
            surface = renpy.display.im.load_surface(self.image)

        self.glTexture, self.width, self.height = utils.glTextureFromSurface(surface)
        if self.glTexture == 0:
            raise RuntimeError("Can't load gl texture from image: %s" % image)

    def free(self):
        if self.glTexture:
            gl.glDeleteTextures(1, self.glTexture)
            self.glTexture = 0

class TextureMap:
    def __init__(self):
        self.textures = {}

    def free(self):
        for sampler, entry in self.textures.items():
            entry.free()
        self.textures.clear()

    def setTexture(self, sampler, image):
        entry = TextureEntry(image, sampler)
        old = self.textures.get(sampler)
        if old:
            old.free()
        self.textures[sampler] = entry

    def bindTextures(self, shader):
        index = 0
        for sampler, entry in self.textures.items():
            shader.uniformi(sampler, index)
            gl.glActiveTexture(gl.GL_TEXTURE0 + index)
            gl.glBindTexture(gl.GL_TEXTURE_2D, entry.glTexture)
            index += 1

    def unbindTextures(self):
        for i in range(len(self.textures)):
            gl.glActiveTexture(gl.GL_TEXTURE0 + i)
            gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
        gl.glActiveTexture(gl.GL_TEXTURE0)


class BaseRenderer(object):
    def __init__(self):
        self.useDepth = False
        self.clearColor = (0, 0, 0, 0)

    def setUniforms(self, shader, uniforms):
        for key, value in uniforms.items():
            if isinstance(value, (int, float)):
                shader.uniformf(key, value)
            elif isinstance(value, euclid.Matrix4):
                shader.uniformMatrix4f(key, utils.matrixToList(value))
            elif len(value) == 16:
                shader.uniformMatrix4f(key, value)
            else:
                shader.uniformf(key, *value)

    def bindAttributeArray(self, shader, name, data, count):
        location = gl.glGetAttribLocation(shader.handle, name)
        if location != -1:
            gl.glVertexAttribPointer(location, count, gl.GL_FLOAT, False, 0, data)
            gl.glEnableVertexAttribArray(location)

    def unbindAttributeArray(self, shader, name):
        location = gl.glGetAttribLocation(shader.handle, name)
        if location != -1:
            gl.glDisableVertexAttribArray(location)

    def setTexture(self, sampler, image):
        raise NotImplementedError("Must be implemented")

    def free(self):
        raise NotImplementedError("Must be implemented")

    def getSize(self):
        raise NotImplementedError("Must be implemented")

    def render(self, context):
        raise NotImplementedError("Must be implemented")


class Renderer2D(BaseRenderer):
    def __init__(self):
        super(Renderer2D, self).__init__()
        self.shader = None
        self.verts = self.createVertexQuad()
        self.textureMap = TextureMap()

    def init(self, image, vertexShader, pixeShader):
        self.shader = utils.Shader(vertexShader, pixeShader)

        self.textureMap.setTexture(shader.TEX0, image)

    def setTexture(self, sampler, image):
        self.textureMap.setTexture(sampler, image)

    def free(self):
        if self.textureMap:
            self.textureMap.free()
            self.textureMap = None

        if self.shader:
            self.shader.free()
            self.shader = None

    def getSize(self):
        tex = self.textureMap.textures[shader.TEX0]
        return tex.width, tex.height

    def createVertexQuad(self):
        tx2 = 1.0 #Adjust if rounding textures to power of two
        ty2 = 1.0
        vertices = [
            -1, -1, 0.0, 0.0, #Bottom left
            1, -1, tx2, 0.0, #Bottom right
            -1, 1, 0.0, ty2, #Top left
            1, 1, tx2, ty2, #Top right
        ]
        return (gl.GLfloat * len(vertices))(*vertices)

    def render(self, context):
        self.shader.bind()

        flipY = -1
        projection = utils.createPerspectiveOrtho(-1.0, 1.0, 1.0 * flipY, -1.0 * flipY, -1.0, 1.0)
        self.shader.uniformMatrix4f(shader.PROJECTION, projection)
        self.shader.uniformf("imageSize", *self.getSize())

        self.setUniforms(self.shader, context.uniforms)

        self.textureMap.bindTextures(self.shader)

        gl.glClearColor(*self.clearColor)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        self.bindAttributeArray(self.shader, "inVertex", self.verts, 4)
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, len(self.verts) // 4);
        self.unbindAttributeArray(self.shader, "inVertex")

        self.textureMap.unbindTextures()

        self.shader.unbind()



def createDefaultMatrices(width, height, context):
    eye = euclid.Vector3(0, 0, -5)
    at = euclid.Vector3(0, 0, 0)
    up = euclid.Vector3(0, 1, 0)
    view = euclid.Matrix4.new_look_at(eye, at, up)
    projection = utils.createPerspective(60, width, height, 0.1, 100)
    return view, projection

class ModelEntry:
    def __init__(self, mesh, matrix):
        self.mesh = mesh
        self.matrix = matrix
        self.textureMap = TextureMap()

    def free(self):
        self.textureMap.free()
        self.textureMap = None

class Renderer3D(BaseRenderer):
    def __init__(self):
        super(Renderer3D, self).__init__()
        self.useDepth = True
        self.width = 0
        self.height = 0
        self.shader = None
        self.models = {}

    def init(self, vertexShader, pixelShader, width, height):
        self.width = width
        self.height = height
        self.shader = utils.Shader(vertexShader, pixelShader)

    def setTexture(self, sampler, image):
        self.models.itervalues().next().textureMap.setTexture(sampler, image)

    def free(self):
        for tag, entry in self.models.items():
            entry.free()
        self.models.clear()

    def getModel(self, tag):
        return self.models.get(tag)

    def loadModel(self, tag, path, textures, matrix=None):
        if not matrix:
            matrix = euclid.Matrix4()

        m = mesh.MeshObj(path)
        m.load()

        entry = ModelEntry(m, matrix)
        for sampler, image in textures.items():
            entry.textureMap.setTexture(sampler, image)

        old = self.models.get(tag)
        if old:
            old.free()
        self.models[tag] = entry

        return entry

    def getSize(self):
        return self.width, self.height

    def render(self, context):
        self.shader.bind()

        gl.glDisable(gl.GL_BLEND)
        gl.glEnable(gl.GL_DEPTH_TEST)

        gl.glClearDepth(1.0)
        gl.glClearColor(*self.clearColor)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

        view, projection = createDefaultMatrices(self.width, self.height, context)
        self.shader.uniformMatrix4f(shader.VIEW_MATRIX, view)
        self.shader.uniformMatrix4f(shader.PROJ_MATRIX, projection)

        self.setUniforms(self.shader, context.uniforms)

        for tag, entry in self.models.items():
            mesh = entry.mesh

            entry.textureMap.bindTextures(self.shader)

            self.shader.uniformMatrix4f(shader.WORLD_MATRIX, entry.matrix)

            self.bindAttributeArray(self.shader, "inPosition", mesh.vertices, 3)
            self.bindAttributeArray(self.shader, "inNormal", mesh.normals, 3)
            self.bindAttributeArray(self.shader, "inUv", mesh.uvs, 2)
            gl.glDrawArrays(gl.GL_TRIANGLES, 0, len(mesh.vertices) // 3)
            self.unbindAttributeArray(self.shader, "inPosition")
            self.unbindAttributeArray(self.shader, "inNormal")
            self.unbindAttributeArray(self.shader, "inUv")

            entry.textureMap.unbindTextures()

        gl.glEnable(gl.GL_BLEND)
        gl.glDisable(gl.GL_DEPTH_TEST)

        self.shader.unbind()

class SkinnedRenderer(BaseRenderer):
    def __init__(self):
        super(SkinnedRenderer, self).__init__()
        self.shader = None
        self.textureMap = TextureMap()
        self.skinTextures = TextureMap()

    def init(self, image, vertexShader, pixeShader):
        self.shader = utils.Shader(vertexShader, pixeShader)

        self.textureMap.setTexture(shader.TEX0, image)

    def setTexture(self, sampler, image):
        self.textureMap.setTexture(sampler, image)

    def free(self):
        if self.textureMap:
            self.textureMap.free()
            self.textureMap = None

        if self.skinTextures:
            self.skinTextures.free()
            self.skinTextures = None

        if self.shader:
            self.shader.free()
            self.shader = None

    def getSize(self):
        #tex = self.textureMap.textures[shader.TEX0]
        #return tex.width, tex.height
        return self.metadata["width"], self.metadata["height"]

    def createVertexQuad(self, bone):
        tx2 = 1.0 #Adjust if rounding textures to power of two
        ty2 = 1.0

        meta = self.metadata
        rect = bone["crop"]

        # x1 = (float(rect[0]) / meta["width"]) * 2
        # x2 = (float(rect[2]) / meta["width"]) * 2

        # y1 = (float(rect[1]) / meta["height"]) * 2
        # y2 = (float(rect[3]) / meta["height"]) * 2

        #w = (float(rect[2] - rect[0]) / meta["width"])
        #h = (float(rect[3] - rect[1]) / meta["width"])

        w = float(rect[2] - rect[0])
        h = float(rect[3] - rect[1])

        vertices = [
            #Note y-axis is upside down
            0, 0, 0.0, 0.0, #Bottom left
            w, 0, tx2, 0.0, #Bottom right
            0, h, 0.0, ty2, #Top left
            w, h, tx2, ty2, #Top right

            #0 - w, 0 - h, 0.0, 0.0, #Bottom left
            #0 + w, 0 - h, tx2, 0.0, #Bottom right
            #0 - w, 0 + h, 0.0, ty2, #Top left
            #0 + w, 0 + h, tx2, ty2, #Top right

            #-1 + x1, -1 + y1, 0.0, 0.0, #Bottom left
            #-1 + x2, -1 + y1, tx2, 0.0, #Bottom right
            #-1 + x1, -1 + y2, 0.0, ty2, #Top left
            #-1 + x2, -1 + y2, tx2, ty2, #Top right

            # -1, -1, 0.0, 0.0, #Bottom left
            # 1, -1, tx2, 0.0, #Bottom right
            # -1, 1, 0.0, ty2, #Top left
            # 1, 1, tx2, ty2, #Top right
        ]
        return (gl.GLfloat * len(vertices))(*vertices)

    def render(self, context):
        self.shader.bind()

        self.shader.uniformf("imageSize", *self.getSize())

        self.setUniforms(self.shader, context.uniforms)

        #self.textureMap.bindTextures(self.shader)

        gl.glClearColor(*self.clearColor)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        screen = self.getSize()
        self.shader.uniformf("screenSize", *screen)

        for i, bone in enumerate(self.metadata["bones"]):
            tex = self.skinTextures.textures[bone["name"] + ".image"]

            self.shader.uniformi(shader.TEX0, 0)
            gl.glActiveTexture(gl.GL_TEXTURE0 + 0)
            gl.glBindTexture(gl.GL_TEXTURE_2D, tex.glTexture)

            flipY = -1
            projection = utils.createPerspectiveOrtho(-1.0, 1.0, 1.0 * flipY, -1.0 * flipY, -1.0, 1.0)
            transform = euclid.Matrix4()

            matrix = euclid.Matrix4()
            for i, attr in enumerate("abcdefghijklmnop"):
                setattr(matrix, attr, projection[i])

            xPixel = (1.0 / screen[0]) * 2
            yPixel = (1.0 / screen[1]) * 2
            head = bone["head"]

            crop = bone["crop"]
            self.shader.uniformf("crop", *crop)

            w = float(crop[2] - crop[0])
            h = float(crop[3] - crop[1])
            xMove = -(screen[0] / 2.0) + w / 2
            yMove = -(screen[1] / 2.0) + h / 2

            transform.translate(crop[0] * xPixel, crop[1] * yPixel, 0)
            transform.translate(xMove * xPixel, yMove * yPixel, 0)
            transform.rotatez(math.sin(context.time) * 2)
            transform.translate(-xMove * xPixel, -yMove * yPixel, 0)

            self.shader.uniformMatrix4f("transform", transform)
            self.shader.uniformMatrix4f(shader.PROJECTION, matrix)

            verts = self.createVertexQuad(bone)

            self.bindAttributeArray(self.shader, "inVertex", verts, 4)
            gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, len(verts) // 4);
            self.unbindAttributeArray(self.shader, "inVertex")

        gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

        #self.textureMap.unbindTextures()

        self.shader.unbind()


    def loadTest(self):
        surface = pygame.image.load("E:/vn/skeleton/combined/combined.png")
        self.setTexture(shader.TEX0, surface)

        with open("E:/vn/skeleton/combined/combined.json") as meta:
            self.metadata = json.load(meta)

        self.loadMetadataImages()

    def loadSkinImage(self, bone):
        for imageType in ["image", "imageWeights"]:
            surface = pygame.image.load("E:/vn/skeleton/combined/" + bone[imageType])
            self.skinTextures.setTexture(bone["name"] + "." + imageType, surface)

    def loadMetadataImages(self):
        for bone in self.metadata["bones"]:
            self.loadSkinImage(bone)
            #surface = pygame.image.load("E:/vn/skeleton/combined/" + bone["image"])
            #self.skinTextures.setTexture(bone["name"] + ".image", surface)

            #shader.log("Loading bone: %s" % bone["name"])
