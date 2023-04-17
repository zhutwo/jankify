# FROM BLENDER PYTHON CONSOLE
# import os
# filename = os.path.join( os.path.dirname( bpy.data.filepath ) , "scripts\\jankify.py" )
# exec( compile( open( filename ).read(), filename, 'exec'))

# MAKE SURE THE FILE IS SAVED FIRST! Otherwise it won't locate the necessary folders.


import bmesh
import bpy  # used for auto-complete outside of Blender
import math
import os
import random
from datetime import datetime

input_folder = os.path.dirname(bpy.data.filepath) + '\\input'
output_folder = os.path.dirname(bpy.data.filepath) + '\\output'
log_folder = os.path.dirname(bpy.data.filepath) + '\\logs'


def main(d_mode=0, k_fat=4, k_jank=0.15):

    print("Hi! I'm going to parse the input folder :)")

    if (not os.path.exists(input_folder)):
        print("I'll need input and output folders. Please make these:")
        print(input_folder + "\\")
        print(output_folder + "\\")
        return

    if (not os.path.exists(log_folder)):
        print("Log folder not found. Making one...")
        os.mkdir(log_folder)

    log_path = os.path.join(log_folder, datetime.today().strftime(
        '%Y-%m-%d-%H-%M-%S')) + "-chunkifier.txt"
    log_file = open(log_path, "w")

    fbx_count = 0
    for entry in os.scandir(input_folder):
        if (entry.path.endswith(".fbx") and entry.is_file()):
            fbx_count += 1
            process_file(entry.path, log_file, d_mode, k_fat, k_jank)

    print(f'Processed {fbx_count} files from {input_folder}\\')

    log_file.close()


def process_file(import_path, log_file, d_mode, k_fat, k_jank):

    # Locate the model to import.
    print(f'Processing { import_path }...')
    bpy.ops.import_scene.fbx(filepath=import_path)

    # Select all objects in the scene.
    bpy.ops.object.select_all(action='SELECT')

    # Are there multiple objects in the scene?
    has_multiple_objects = len(bpy.context.selected_objects) > 1
    print(f'has_multiple_objects: { has_multiple_objects }.')

    # Log file name
    if has_multiple_objects:
        log_file.write(os.path.join(os.path.basename(import_path), "\n"))

    # Assign a target. Without an active object, Blender will throw an error when entering EDIT mode
    target = bpy.context.selected_objects[0]
    bpy.context.view_layer.objects.active = target

    # Apply a Shrink/Fatten modifier.
    if k_fat != 0:
        fatten(target, k_fat)

    # Apply scale before saving
    bpy.ops.object.transform_apply(scale=True, location=False, rotation=True)

    # Nudge vertices in random directions.
    jankify(target, d_mode, k_jank)

    # Determine output path and save the file.
    output_path = str(import_path).replace("input", "output")
    bpy.ops.export_scene.fbx(filepath=output_path, path_mode='ABSOLUTE')

    # Clean up after ourselves. Remove any remaining models.
    bpy.ops.object.delete()


def fatten(target, k_fat):

    # Get the longest side
    longest = target.dimensions[0]
    if (target.dimensions[1] > longest):
        longest = target.dimensions[1]
    if (target.dimensions[2] > longest):
        longest = target.dimensions[2]

    # How much to fatten the item.
    fat_factor = longest * k_fat

    # Switch to EDIT mode. Context is now different.
    bpy.ops.object.mode_set(mode='EDIT')

    # Select all vertices and shrink / fatten
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.transform.shrink_fatten(value=fat_factor)

    # De-select, to return to object mode.
    bpy.ops.object.mode_set(mode='OBJECT')


def jankify(target, d_mode, k_jank):

    # Switch to EDIT mode. Required for bmesh
    bpy.ops.object.mode_set(mode='EDIT')

    sphere_ratio = 0.5
    dist_ratio = 0.5

    tm = bmesh.from_edit_mesh(target.data)
    # Necessary - https://blender.stackexchange.com/a/31750
    tm.verts.ensure_lookup_table()

    neighbours = {}
    for vert in tm.verts:
        neighbours[vert] = get_adjacent_vertices(vert)

    for vert in tm.verts:

        _sum = 0.0
        _count = 0
        max_dist = None
        min_dist = None
        dist_vectors = []

        for n in neighbours[vert]:
            dist = get_distance_between(vert.co, n)
            vec = subtract(n, vert.co)
            obj = {'d': dist, 'v': vec}
            dist_vectors.append(obj)
            if max_dist == None:
                max_dist = dist
            elif dist > max_dist:
                max_dist = dist
            if min_dist == None:
                min_dist = dist
            elif dist < min_dist:
                min_dist = dist
            _sum += dist
            _count += 1
            print(f'original: {vert.co} \nneighbor: {n}')

        print("-----------------------")

        avg_dist = _sum/_count
        rand_bias = [0.0, 0.0, 0.0]

        for obj in dist_vectors:
            weight = (1.0 - obj['d']/max_dist)/_count
            bias_vector = scale(normalize(obj['v']), weight)
            rand_bias = subtract(rand_bias, bias_vector)

        rand_vector = [random.random()*2.0 - 1.0 + rand_bias[0], random.random()
                       * 2.0 - 1.0 + rand_bias[1], random.random()*2.0 - 1.0 + rand_bias[2]]
        rand_vector = normalize(rand_vector)
        rand_factor = random.random()
        if d_mode == 0:
            d = avg_dist
        elif d_mode == 1:
            d = min_dist
        elif d_mode == 2:
            d = max_dist
        else:
            print("ERROR: Invalid d_mode parameter!")
            return
        rand_length = rand_factor * k_jank * d
        rand_vector = scale(rand_vector, rand_length)

        for n in neighbours[vert]:
            v = subtract(n, vert.co)
            theta = abs(get_angle_between(rand_vector, v))
            if theta < math.pi/3.0:  # if neighbour vector is within 120 degrees of random vector and at risk of conflict
                dist = length(v)
                sphere_radius = dist * sphere_ratio
                # if random vector intersects exclusion sphere around neighbour
                if math.sin(theta) * dist < sphere_radius:
                    sect_dist = find_intersect_distance(
                        sphere_radius, theta, dist)
                    if rand_length > sect_dist:
                        # recalculate length using exclusion sphere distance
                        rand_vector = scale(
                            normalize(rand_vector), sect_dist * rand_factor)
                else:
                    if rand_length > dist * dist_ratio:
                        # recalculate length using max distance ratio
                        rand_vector = scale(
                            normalize(rand_vector), dist * dist_ratio * rand_factor)

        # not sure if have to assign as temp var first
        vert.co = add(vert.co, rand_vector)

    # De-select, to return to object mode.
    bpy.ops.object.mode_set(mode='OBJECT')


### HELPERS

def find_intersect_distance(radius, theta, dist):
    l_opp = math.sin(theta) * dist
    l_adj_radius = math.sqrt(radius*radius - l_opp*l_opp)
    l_adj_dist = math.cos(theta) * dist
    l_final = l_adj_dist - l_adj_radius
    return l_final


def get_angle_between(v1, v2):
    angle = math.acos((v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]) / (math.sqrt(v1[0]*v1[0] + v1[1]*v1[1] + v1[2]*v1[2]) * math.sqrt(v2[0]*v2[0] + v2[1]*v2[1] + v2[2]*v2[2])))
    return angle


def get_distance_between(v1, v2):
    v = subtract(v1, v2)
    dist = length(v)
    return dist


def length(v):
    length = math.sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2])
    return length


def normalize(v):
    l = length(v)
    normalized = [v[0]/l, v[1]/l, v[2]/l]
    return normalized


def scale(v, f):
    v = [v[0]*f, v[1]*f, v[2]*f]
    return v


def add(v1, v2):
    v = [v1[0] + v2[0], v1[1] + v2[1], v1[2] + v2[2]]
    return v


def subtract(v1, v2):
    v = [v1[0] - v2[0], v1[1] - v2[1], v1[2] - v2[2]]
    return v


def get_adjacent_vertices(v):
    # print(v.link_edges)
    adjacent = []

    for edge in v.link_edges:
        v_other = edge.other_vert(v)
        # print("%d -> %d via edge %d" % (v.index, v_other.index, e.index))
        adjacent.append(list(v_other.co))

    # print(f'adjacent: {adjacent}')
    return adjacent


### RUN
# d_mode: 0 = avg, 1 = min, 2 = max (mode for distance calculation)
main(d_mode=0, k_fat=2, k_jank=0.15)
