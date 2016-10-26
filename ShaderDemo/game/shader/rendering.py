
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
import geometry

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


class SkinningContext:
    def __init__(self):
        self.boneStack = []
        self.matrixStack = []

    def push(self, bone, m):
        self.boneStack.append(bone)
        self.matrixStack.append(m)

    def pop(self):
        self.boneStack.pop()
        self.matrixStack.pop()


class SkinnedBone:
    def __init__(self, data, surface):
        self.data = data
        self.vertices, self.indices = self.computeQuad(surface)

    def computeQuad(self, surface):
        rect = self.data["crop"]
        w = float(rect[2] - rect[0])
        h = float(rect[3] - rect[1])

        gridSize = 10
        vertices, uvs, indices = geometry.createGrid((0, 0, w, h), None, gridSize, gridSize)

        verts = []
        for i in range(len(vertices)):
            verts.append(vertices[i][0])
            verts.append(vertices[i][1])

            xUv = uvs[i][0]
            yUv = uvs[i][1]
            verts.append(xUv)
            verts.append(yUv)

        return (gl.GLfloat * len(verts))(*verts), (gl.GLuint * len(indices))(*indices)

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
        return self.metadata["width"], self.metadata["height"]

    def render(self, context):
        self.shader.bind()

        self.shader.uniformf("imageSize", *self.getSize())

        self.setUniforms(self.shader, context.uniforms)

        #self.textureMap.bindTextures(self.shader)

        gl.glClearColor(*self.clearColor)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        screenSize = self.getSize()
        self.shader.uniformf("screenSize", *screenSize)

        base = euclid.Matrix4()
        #base.rotatey(math.sin(context.time))

        skinning = SkinningContext()
        skinning.push(None, base)

        self.renderBone(self.root, skinning, context)

        skinning.pop()

        for i in range(2):
            gl.glActiveTexture(gl.GL_TEXTURE0 + i)
            gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

        gl.glActiveTexture(gl.GL_TEXTURE0)

        #self.textureMap.unbindTextures()

        self.shader.unbind()

    def renderBone(self, bone, skinning, context):
        data = bone.data

        screenSize = self.getSize()
        tex = self.skinTextures.textures[data["name"] + ".image"]
        texWeights = self.skinTextures.textures[data["name"] + ".imageWeights"]

        self.shader.uniformi(shader.TEX0, 0)
        gl.glActiveTexture(gl.GL_TEXTURE0 + 0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, tex.glTexture)

        self.shader.uniformi("weightTex1", 1)
        gl.glActiveTexture(gl.GL_TEXTURE0 + 1)
        gl.glBindTexture(gl.GL_TEXTURE_2D, texWeights.glTexture)

        flipY = -1
        projection = utils.createPerspectiveOrtho(-1.0, 1.0, 1.0 * flipY, -1.0 * flipY, -1.0, 1.0)
        transformParent = skinning.matrixStack[-1]
        transform = euclid.Matrix4() * transformParent

        matrix = euclid.Matrix4()
        for i, attr in enumerate("abcdefghijklmnop"):
            setattr(matrix, attr, projection[i])

        xPixel = (1.0 / screenSize[0]) * 2
        yPixel = (1.0 / screenSize[1]) * 2

        crop = data["crop"]
        self.shader.uniformf("crop", *crop)

        w = float(crop[2] - crop[0])
        h = float(crop[3] - crop[1])
        xMove = -(screenSize[0] / 2.0)# + w / 2
        yMove = -(screenSize[1] / 2.0)# + h / 2

        xParent = 0
        yParent = 0
        parent = skinning.boneStack[-1]
        if parent:
            parentCrop = parent["crop"]
            xParent, yParent = parentCrop[0], parentCrop[1]

        transform.translate((crop[0] - xParent) * xPixel, (crop[1] - yParent) * yPixel, 0)

        self.shader.uniformMatrix4f("transformBase", transform)

        if data["name"] in ("lShldr", "lForeArm", "lHand", "neck"):
            head = data["head"]
            xMove += head[0] - crop[0]
            yMove += head[1] - crop[1]

            transform.translate(xMove * xPixel, yMove * yPixel, 0)
            transform.rotatez(math.sin(context.time))
            transform.translate(-xMove * xPixel, -yMove * yPixel, 0)

        self.shader.uniformMatrix4f("transform", transform)
        self.shader.uniformMatrix4f(shader.PROJECTION, matrix)
        self.shader.uniformf("wireFrame", 0)

        self.bindAttributeArray(self.shader, "inVertex", bone.vertices, 4)
        gl.glDrawElements(gl.GL_TRIANGLES, len(bone.indices), gl.GL_UNSIGNED_INT, bone.indices)

        if 0:
            self.shader.uniformf("wireFrame", 1)
            gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_LINE)
            gl.glDrawElements(gl.GL_TRIANGLES, len(bone.indices), gl.GL_UNSIGNED_INT, bone.indices)
            gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_FILL)

        self.unbindAttributeArray(self.shader, "inVertex")

        skinning.push(data, transform)

        for childName in data["children"]:
            self.renderBone(self.bones[childName], skinning, context)

        skinning.pop()

    def loadTest(self):
        surface = pygame.image.load("E:/vn/skeleton/combined/combined.png")
        self.setTexture(shader.TEX0, surface)

        with open("E:/vn/skeleton/combined/combined.json") as meta:
            self.metadata = json.load(meta)

        self.bones = {}
        for bone in self.metadata["bones"]:
            surfaces = self.loadSkinImages(bone)
            self.bones[bone["name"]] = SkinnedBone(bone, surfaces[0])

        self.root = self.bones[self.findRootName(self.metadata)]

    def loadSkinImages(self, bone):
        surfaces = []
        for imageType in ["image", "imageWeights"]:
            surface = pygame.image.load("E:/vn/skeleton/combined/" + bone[imageType])
            self.skinTextures.setTexture(bone["name"] + "." + imageType, surface)
            surfaces.append(surface)
        return surfaces

    def findRootName(self, metadata):
        children = set()
        for bone in metadata["bones"]:
            children.update(bone["children"])

        for bone in metadata["bones"]:
            if bone["name"] not in children:
                return bone["name"]
        return None