
import pygame
import euclid
import utils

class KeyFrame:
    def __init__(self):
        self.pivot = None
        self.rotation = None
        self.scale = None
        self.zOrder = None
        self.visible = None

def copyKeyData(source, target):
    target.pivot = (source.pivot[0], source.pivot[1])
    target.rotation = euclid.Vector3(source.rotation.x, source.rotation.y, source.rotation.z)
    target.scale = euclid.Vector3(source.scale.x, source.scale.y, source.scale.z)
    target.zOrder = source.zOrder
    target.visible = source.visible

def keyDataChanged(a, b):
    if a.pivot != b.pivot:
        return True
    if a.rotation != b.rotation:
        return True
    if a.scale != b.scale:
        return True
    if a.zOrder != b.zOrder:
        return True
    if a.visible != b.visible:
        return True
    return False

def interpolateKeyData(a, b, weight):
    key = KeyFrame()
    key.pivot = utils.interpolate2d(a.pivot, b.pivot, weight)
    key.rotation = euclid.Vector3(*utils.interpolate3d(a.rotation, b.rotation, weight))
    key.scale = euclid.Vector3(*utils.interpolate3d(a.scale, b.scale, weight))
    key.zOrder = a.zOrder
    key.visible = a.visible
    return key

class Frame:
    def __init__(self):
        self.keys = {}

    def getBoneKey(self, name):
        key = self.keys.get(name)
        if not key:
            key = KeyFrame()
            self.keys[name] = key
        return key

class SkinnedAnimation:
    def __init__(self):
        self.frames = [Frame()]

    def setFrameCount(self, count):
        self.frames = self.frames[:count]
        while len(self.frames) < count:
            self.frames.append(Frame())

    def update(self, frameNumber, editor):
        for event, pos in editor.context.events:
            if event.type == pygame.KEYDOWN:
                key = event.unicode
                if key == "i":
                    bone = editor.getActiveBone()
                    if bone:
                        key = self.frames[frameNumber].getBoneKey(bone.name)
                        copyKeyData(bone, key)

        self.cleanupDuplicateKeys(editor.getBones(), frameNumber)

    def cleanupDuplicateKeys(self, bones, frameNumber):
        for name, bone in bones.items():
            keys = self.getBoneKeyFrames(name)
            duplicates = set()
            i = 0
            while i < len(keys):
                index = keys[i]
                i2 = i + 1

                while i2 < len(keys):
                    index2 = keys[i2]
                    if not keyDataChanged(self.frames[index].keys[name], self.frames[index2].keys[name]):
                        if index == frameNumber:
                            duplicates.add(index)
                        elif index2 == frameNumber:
                            duplicates.add(index2)
                    i2 += 1
                i += 1

            for index in duplicates:
                if index > 0:
                    del self.frames[index].keys[name]

    def drawDebug(self, editor, frameNumber):
        height = 20
        color = (255, 0, 0)
        x = 400
        y = 10
        for i, frame in enumerate(self.frames):
            if frame.keys: # i > 0 and
                editor.drawText("Frame %i:" % i, color, (x, y))
                y += height
                for name, key in frame.keys.items():
                    editor.drawText("Key %s" % name, (255, 255, 0), (x, y))
                    y += height

    def getBoneKeyFrames(self, name):
        results = []
        for i, frame in enumerate(self.frames):
            if name in frame.keys:
                results.append(i)
        return results

    def updateBones(self, bones):
        #TODO Remove frames that had their bones:
        # -removed
        # -renamed
        # -etc...
        pass

    def findKeyFrameRange(self, frameNumber, bone):
        start = None
        end = None

        i = frameNumber
        while i >= 0:
            if bone.name in self.frames[i].keys:
                start = i
                break
            i -= 1

        i = frameNumber
        while i < len(self.frames):
            if bone.name in self.frames[i].keys:
                end = i
                break
            i += 1

        return start, end

    def apply(self, frameNumber, bones):
        frame = self.frames[frameNumber]

        for name, bone in bones.items():
            start, end = self.findKeyFrameRange(frameNumber, bone)
            if start is not None and end is not None:
                startKey = self.frames[start].keys[name]
                endKey = self.frames[end].keys[name]
                if startKey == endKey:
                    copyKeyData(startKey, bone)
                else:
                    weight = float(frameNumber - start) / (end - start)
                    key = interpolateKeyData(startKey, endKey, weight)
                    copyKeyData(key, bone)
