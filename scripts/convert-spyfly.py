"""Convert the attributed OpenGameArt Spy Fly source blend into runtime GLB."""

import bpy

# The source includes a camera used only for the preview. Keep mesh/materials,
# drop cameras/lights so the WebGL scene owns lighting and framing.
bpy.ops.object.select_all(action="DESELECT")
for obj in list(bpy.data.objects):
    if obj.type in {"CAMERA", "LIGHT"} or obj.name.lower() in {"cam", "camera"}:
        bpy.data.objects.remove(obj, do_unlink=True)

meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
for obj in meshes:
    obj.select_set(True)
    # Keep the recognizable compound-eye/wings silhouette while making six
    # simultaneous copies practical on a laptop GPU.
    modifier = obj.modifiers.new(name="FlyPokerRuntimeDecimate", type="DECIMATE")
    modifier.ratio = 0.10
bpy.context.view_layer.objects.active = meshes[0] if meshes else None
for obj in meshes:
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier="FlyPokerRuntimeDecimate")

bpy.ops.export_scene.gltf(
    filepath="public/models/spyfly.glb",
    export_format="GLB",
    export_apply=True,
    export_animations=False,
    export_materials="EXPORT",
)
