
import math
import json
import ctypes

import pygame
import euclid
import skinned

pygame.font.init()
FONT = pygame.font.Font(None, 20)

PICK_DISTANCE_PIVOT = 20
PICK_DISTANCE_CROP = 5

DRAG_PIVOT = "dragPivot"
DRAG_POS = "dragPos"
ACTIVE_BONE_NAME = "activeBoneName"
MOUSE = "mouse"
MODE = "mode"

def lineToPoint(a, b, point):
    x1, y1 = a
    x2, y2 = b
    x3, y3 = point

    px = x2 - x1
    py = y2 - y1
    value = px*px + py*py

    u =  ((x3 - x1) * px + (y3 - y1) * py) / float(value)
    if u > 1:
        u = 1
    elif u < 0:
        u = 0

    x = x1 + u * px
    y = y1 + u * py
    dx = x - x3
    dy = y - y3
    return math.sqrt(dx*dx + dy*dy)

class AttributeEdit:
    def __init__(self, editor, bone, attribute, mouse):
        self.bone = bone
        self.attribute = attribute
        self.mouse = mouse
        self.original = self.getValue()
        self.pivot = editor.getBonePivotTransformed(bone)
        self.value = self.original + math.atan2(mouse[0] - self.pivot[0], mouse[1] - self.pivot[1])

    def getValue(self):
        v = self.bone
        for attr in self.attribute.split("."):
            v = getattr(v, attr)
        return v

    def setValue(self, value):
        v = self.bone
        attrs = self.attribute.split(".")
        for attr in attrs[:-1]:
            v = getattr(v, attr)
        setattr(v, attrs[-1], value)

    def cancel(self, editor):
        self.setValue(self.original)

    def apply(self, editor):
        pass

    def update(self, editor):
        angle = math.atan2(editor.mouse[0] - self.pivot[0], editor.mouse[1] - self.pivot[1])
        self.setValue(self.value - angle)

    def draw(self, editor):
        name = self.attribute[0].upper()
        value = self.getValue()
        if "rotation" in self.attribute:
            value = math.degrees(value)

        editor.context.overlayCanvas.line("#f00", (self.pivot.x, self.pivot.y), editor.mouse)
        editor.drawText("%s: %.1f" % (name, value), "#fff", (editor.mouse[0] + 20, editor.mouse[1]))


class ExtrudeBone:
    def __init__(self, editor, bone, mouse):
        self.bone = bone
        self.mouse = mouse
        self.pivot = editor.getBonePivotTransformed(bone)

    def findNextFreeBoneName(self, bones, base):
        index = 1
        while 1:
            name = "%s %i" % (base, index)
            if not name in bones:
                return name
            index += 1

    def cancel(self, editor):
        pass

    def apply(self, editor):
        bones = editor.context.renderer.bones
        parent = bones[self.bone.name]

        parts = parent.name.strip().split(" ")
        if parts[-1].isdigit():
            parts = parts[:-1]
        newName =  self.findNextFreeBoneName(bones, " ".join(parts))

        bone = skinned.Bone(newName)
        bone.pivot = editor.mouse
        bone.zOrder = parent.zOrder + 1
        bones[bone.name] = bone

        editor.connectBone(bone.name, parent.name)
        editor.setActiveBone(bone)

    def update(self, editor):
        pass

    def draw(self, editor):
        editor.context.overlayCanvas.line("#f00", (self.pivot.x, self.pivot.y), editor.mouse)
        editor.context.overlayCanvas.circle(self.bone.color, editor.mouse, 8)

class PoseMode:
    def __init__(self):
        self.editor = None
        self.active = None

    def update(self, editor):
        self.editor = editor

    def handleEvent(self, event):
        event, pos = event
        if event.type == pygame.KEYDOWN:
            activeBone = self.editor.getActiveBone()
            if event.unicode == "h" and activeBone:
                activeBone.visible = not activeBone.visible
                return True
            if event.unicode == "r" and activeBone:
                self.newEdit(AttributeEdit(self.editor, activeBone, "rotation.z", pos))
                return True
            if event.unicode == "s" and activeBone:
                self.newEdit(AttributeEdit(self.editor, activeBone, "scale.y", pos))
                return True
            if event.unicode == "e" and activeBone:
                self.newEdit(ExtrudeBone(self.editor, activeBone, pos))
                return True
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.active:
                if event.button == 1:
                    self.active.apply(self.editor)
                if event.button == 3:
                    self.active.cancel(self.editor)
                self.active = None
                return True

        return False

    def newEdit(self, edit):
        if self.active:
            self.active.cancel(self.editor)
        self.active = edit

    def draw(self):
        if self.active:
            self.active.update(self.editor)
            self.active.draw(self.editor)


class SkinnedEditor:
    def __init__(self, context, settings):
        self.context = context
        self.settings = settings
        self.mouse = (0, 0)
        self.transforms = context.renderer.computeBoneTransforms(context)
        self.transformsMap = self.getTransformsDict()

        self.mode = self.get(MODE)
        if not self.mode:
            self.mode = PoseMode()
            self.set(MODE, self.mode)
        self.mode.update(self)


    def update(self):
        #self.debugAnimate(self.settings["debugAnimate"])
        self.handleEvents()
        self.visualizeBones()

    def saveToFile(self):
        skinned.saveToFile(self.context.renderer.bones, "bones.json")

    def get(self, key):
        return self.context.store.get(key)

    def set(self, key, value):
        self.context.store[key] = value

    def getActiveBone(self):
        bones = self.context.renderer.bones
        name = self.get(ACTIVE_BONE_NAME)
        if name in bones:
            return bones[name]
        return None

    def setActiveBone(self, bone):
        if bone:
            self.set(ACTIVE_BONE_NAME, bone.name)
        else:
            self.set(ACTIVE_BONE_NAME, None)

    def getBone(self, name):
        return self.context.renderer.bones[name]

    def debugAnimate(self, animate):
        context = self.context
        #TODO Rotate all bones that have a parent other than root
        BASE = "doll base"
        self.connectBone("doll lforearm", BASE)
        self.connectBone("doll larm", "doll lforearm")
        self.connectBone("doll lhand", "doll larm")
        self.connectBone("doll hair", BASE)
        self.connectBone("doll skirt", BASE)

        for name in ("doll hair", "doll lforearm", "doll larm", "doll lhand"):
            bone = self.getBone(name)
            if animate:
                bone.rotation.z = math.sin(context.time * 0.5)
            #else:
            #    bone.rotation.z = 0.0

    def drawText(self, text, color, pos):
        surface = FONT.render(text, True, color)
        self.context.overlayCanvas.get_surface().blit(surface, pos)

    def connectBone(self, boneName, parentName):
        bones = self.context.renderer.bones
        poseBone = bones[boneName]
        newParent = bones[parentName]

        oldParent = None
        if poseBone.parent in bones:
            oldParent = bones[poseBone.parent]

        if boneName not in newParent.children:
            if oldParent:
                oldParent.children.remove(boneName)
            newParent.children.append(boneName)
            poseBone.parent = newParent.name

    def handleEvents(self):
        self.mouse = self.get(MOUSE)

        for event, pos in self.context.events:
            self.mouse = pos

            handled = self.mode.handleEvent((event, pos))
            if not handled:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    self.handleMouseDown(pos)
                elif event.type == pygame.MOUSEMOTION:
                    self.handleMouseMotion(pos)
                elif event.type == pygame.MOUSEBUTTONUP:
                    self.handleMouseUp(pos)

        if self.mouse:
            self.set(MOUSE, self.mouse)

    def handleMouseDown(self, pos):
        self.stopDrag()

        bone = None
        if self.settings["pivots"]:
            bone = self.pickPivot(pos)
            if bone:
                self.setActiveBone(bone)
                self.set(DRAG_PIVOT, (bone, pos, bone.pivot))
            else:
                self.setActiveBone(None)
                self.set(DRAG_PIVOT, None)

        if self.settings["imageAreas"] and not bone:
            bone = self.pickCrop(pos)
            if bone:
                self.set(DRAG_POS, (bone, pos, bone.pos))
            else:
                self.set(DRAG_POS, None)

    def handleMouseMotion(self, pos):
        dragPivot = self.get(DRAG_PIVOT)
        if dragPivot:
            bone, oldMouse, oldHead = dragPivot
            delta = (oldMouse[0] - pos[0], oldMouse[1] - pos[1])
            pivot = bone.pivot
            bone.pivot = (oldHead[0] - delta[0], oldHead[1] - delta[1])

        dragPos = self.get(DRAG_POS)
        if dragPos:
            bone, oldMouse, oldPos = dragPos
            delta = (oldMouse[0] - pos[0], oldMouse[1] - pos[1])
            pos = bone.pos
            bone.pos = (oldPos[0] - delta[0], oldPos[1] - delta[1])

    def handleMouseUp(self, pos):
        self.stopDrag()

    def stopDrag(self):
        self.set(DRAG_PIVOT, None)
        self.set(DRAG_POS, None)

    def pickPivot(self, pos):
        closest = None
        closestDistance = None
        for trans in self.transforms:
            bone = trans.bone
            pivot = trans.matrix.transform(self.getBonePivot(bone))
            distance = (pivot - euclid.Vector3(pos[0], pos[1])).magnitude()
            if distance < PICK_DISTANCE_PIVOT:
                if not closest or distance < closestDistance:
                    closest = bone
                    closestDistance = distance
        return closest

    def pickCrop(self, pos):
        closest = None
        closestDistance = None
        for trans in self.transforms:
            if trans.bone.image:
                lines = self.getImageLines(trans.bone)
                for i in range(len(lines) - 1):
                    distance = lineToPoint(lines[i], lines[i + 1], pos)
                    if distance < PICK_DISTANCE_CROP:
                        if not closest or distance < closestDistance:
                            closest = trans.bone
                            closestDistance = distance
        return closest

    def getImageLines(self, bone):
        pos = bone.pos
        image = bone.image
        lines = [
            pos,
            (pos[0] + image.width, pos[1]),
            (pos[0] + image.width, pos[1] + image.height),
            (pos[0], pos[1] + image.height),
            pos
        ]
        return lines

    def getPolyPoints(self, bone):
        points = []
        if bone.points:
            boneMatrix = self.transformsMap[bone.name].matrix
            for point in bone.points:
                pos = boneMatrix.transform(euclid.Vector3(point[0], point[1]))
                points.append((pos.x, pos.y))
        return points

    def getBonePivotTransformed(self, bone):
        return self.transformsMap[bone.name].matrix.transform(self.getBonePivot(bone))

    def getBonePivot(self, bone):
        pivot = bone.pivot
        return euclid.Vector3(pivot[0],  pivot[1], 0)

    def getBonePos(self, bone):
        pos = bone.pos
        return euclid.Vector3(pos[0],  pos[1], 0)

    def getTransformsDict(self):
        mapping = {}
        for trans in self.transforms:
            mapping[trans.bone.name] = trans
        return mapping

    def visualizeBones(self):
        context = self.context
        mouse = self.mouse
        activeBone = self.getActiveBone()

        hoverPivotBone = None
        hoverCropBone = None
        if mouse:
            hoverPivotBone = self.pickPivot(mouse)
            hoverCropBone = self.pickCrop(mouse)

        for trans in self.transforms:
            bone = trans.bone
            bone.wireFrame = ((activeBone and bone.name == activeBone.name) or not activeBone) and self.settings["wireframe"]

            pos = self.getBonePos(bone)
            pivot = self.getBonePivotTransformed(bone)
            activeColor = (0, 255, 0)

            if self.settings["imageAreas"] and bone.image:
                areaColor = (255, 255, 0)
                lines = self.getImageLines(bone)
                if not hoverPivotBone and hoverCropBone and bone.name == hoverCropBone.name:
                    self.drawText(hoverCropBone.name, "#fff", (mouse[0] + 20, mouse[1]))
                    areaColor = activeColor
                context.overlayCanvas.lines(areaColor, False, lines)

                polyPoints = self.getPolyPoints(bone)
                context.overlayCanvas.lines("f00", 1, polyPoints)
                for p in polyPoints:
                    context.overlayCanvas.circle("#0f0", p, 3)

            if self.settings["pivots"]:
                if bone.parent:
                    parentTrans = self.transformsMap[bone.parent]
                    parentBone = parentTrans.bone
                    parentPos = self.getBonePivotTransformed(parentBone)
                    context.overlayCanvas.line("#00f", (pivot.x, pivot.y), (parentPos.x, parentPos.y))

                context.overlayCanvas.circle(bone.color, (pivot.x, pivot.y), 8)
                if hoverPivotBone and bone.name == hoverPivotBone.name:
                    context.overlayCanvas.circle(activeColor, (pivot.x, pivot.y), 4)

                textColor = "#fff"
                if activeBone and bone.name == activeBone.name:
                    textColor = activeColor

                if self.settings["names"]:
                    self.drawText(bone.name, textColor, (pivot.x + 15, pivot.y - 10))

        self.mode.draw()
