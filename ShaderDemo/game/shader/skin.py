
import math
import ctypes
import json
from OpenGL import GL as gl

import rendering
import euclid
import geometry
import delaunay
import skinnedmesh

VERSION = 1
MAX_BONES = 64

def makeArray(tp, values):
    return (tp * len(values))(*values)

class SkinnedImage:
    jsonIgnore = []

    def __init__(self, name, x, y, width, height):
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class SkinningBone:
    jsonIgnore = ["points", "triangles"]

    def __init__(self, name):
        self.name = name
        self.children = []
        self.parent = None
        self.image = None
        self.pos = (0, 0)
        self.pivot = (0, 0)
        self.rotation = euclid.Vector3(0, 0, 0)
        self.scale = euclid.Vector3(1, 1, 1)
        self.zOrder = -1
        self.visible = True
        self.wireFrame = False

        self.mesh = None

        self.points = []
        self.triangles = []

    def getAllChildren(self, bones, results=None):
        if not results:
            results = []

        for name in self.children:
            child = bones[name]
            results.append(child)
            child.getAllChildren(bones, results)
        return results

    def updatePoints(self, surface):
        points = geometry.findEdgePixelsOrdered(surface)
        distance = (surface.get_width() + surface.get_height()) / 10000.0 #TODO Magic
        simplified = geometry.simplifyEdgePixels(points, 40)
        self.points = geometry.offsetPolygon(simplified, -5) #TODO Increase this once better weighting is in?

    def triangulatePoints(self):
        pointsSegments = delaunay.ToPointsAndSegments()
        pointsSegments.add_polygon([self.points])
        triangulation = delaunay.triangulate(pointsSegments.points, pointsSegments.infos, pointsSegments.segments)

        expanded = self.points #geometry.offsetPolygon(self.points, -1) #TODO 0 better, do nothing?
        shorten = 0.5

        self.triangles = []
        for tri in delaunay.TriangleIterator(triangulation, True):
            a, b, c = tri.vertices

            inside = 0
            for line in [(a, b), (b, c), (c, a)]:
                short1, short2 = geometry.shortenLine(line[0], line[1], shorten)
                if geometry.insidePolygon(short1[0], short1[1], expanded) and geometry.insidePolygon(short2[0], short2[1], expanded):
                    inside += 1

            if inside >= 2:
                self.triangles.append(((a[0], a[1]), (b[0], b[1]), (c[0], c[1])))

    def updateMeshFromTriangles(self):
        verts = []
        indices = []
        for tri in self.triangles:
            for v in tri:
                verts.extend([v[0], v[1]])
                indices.append(len(verts) / 2 - 1)

        vCount = len(verts) / 2 / 3
        if vCount != len(self.triangles):
            raise RuntimeError("Invalid vertex count: %i of %i" % (vCount, len(self.triangles)))

        self.mesh = skinnedmesh.SkinnedMesh(makeArray(gl.GLfloat, verts), makeArray(gl.GLuint, indices))

JSON_IGNORES = []

class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (SkinningBone, SkinnedImage, skinnedmesh.SkinnedMesh)):
            d = obj.__dict__.copy()
            for ignore in JSON_IGNORES + getattr(obj, "jsonIgnore", []):
                if ignore in d:
                    del d[ignore]
            return d
        elif isinstance(obj, euclid.Vector3):
            return (obj.x, obj.y, obj.z)
        elif isinstance(obj, ctypes.Array):
            return list(obj)
        return json.JSONEncoder.default(self, obj)

def saveToFile(bones, path):
    data = {
        "version": VERSION,
        "bones": bones
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=1, cls=JsonEncoder, separators=(",", ": "), sort_keys=True)

def _getArray(tp, obj, key):
    data = obj.get(key)
    if data:
        return makeArray(tp, data)
    return None

def loadFromFile(path):
    data = None
    with open(path, "r") as f:
        data = json.load(f)

    if data["version"] != VERSION:
        raise RuntimeError("Invalid version, should be %i" % VERSION)

    bones = {}
    for name, raw in data["bones"].items():
        bone = SkinningBone(raw["name"])
        bone.children = raw["children"]
        bone.parent = raw["parent"]

        image = raw.get("image")
        if image:
            bone.image = SkinnedImage(image["name"], image["x"], image["y"], image["width"], image["height"])

        bone.pos = raw["pos"]
        bone.pivot = raw["pivot"]
        bone.rotation = euclid.Vector3(*raw["rotation"])
        bone.scale = euclid.Vector3(*raw["scale"])
        bone.zOrder = raw["zOrder"]
        bone.visible = raw["visible"]
        bone.wireFrame = raw["wireFrame"]

        mesh = raw.get("mesh")
        if mesh:
            vertices = _getArray(gl.GLfloat, mesh, "vertices")
            indices = _getArray(gl.GLuint, mesh, "indices")
            boneWeights = _getArray(gl.GLfloat, mesh, "boneWeights")
            boneIndices = _getArray(gl.GLfloat, mesh, "boneIndices")
            bone.mesh = skinnedmesh.SkinnedMesh(vertices, indices, boneWeights, boneIndices)

        bones[bone.name] = bone

    return bones
