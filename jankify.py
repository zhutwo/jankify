# FROM BLENDER PYTHON CONSOLE
# import os
# filename = os.path.join( os.path.dirname( bpy.data.filepath ) , "scripts\\jankify.py" )
# exec( compile( open( filename ).read(), filename, 'exec'))

# MAKE SURE THE FILE IS SAVED FIRST! Otherwise it won't locate the necessary folders.

import math
import os
import random
from datetime import datetime
from enum import Enum
import bmesh
import bpy

bl_info = {
    "name": "Jankify",
    "blender": (2, 80, 0),
    "category": "Object",
}

input_folder = os.path.dirname(bpy.data.filepath) + '\\input'
output_folder = os.path.dirname(bpy.data.filepath) + '\\output'
log_folder = os.path.dirname(bpy.data.filepath) + '\\logs'


class DistanceMode(Enum):
    AVG = 0
    MIN = 1
    MAX = 2


def main(d_mode:DistanceMode, fat_factor:float, jank_factor:float):
    print("Hi! I'm going to parse the input folder :)")
    if not os.path.exists(input_folder):
        print("I'll need input and output folders. Please make these:")
        print(input_folder + "\\")
        print(output_folder + "\\")
        return
    if not os.path.exists(log_folder):
        print("Log folder not found. Making one...")
        os.mkdir(log_folder)

    log_path = os.path.join(log_folder, datetime.today().strftime(
        '%Y-%m-%d-%H-%M-%S')) + "-jankifier.txt"
    log_file = open(log_path, "w")

    fbx_count = 0
    for entry in os.scandir(input_folder):
        if entry.path.endswith(".fbx") and entry.is_file():
            fbx_count += 1
            process_file(entry.path, d_mode, fat_factor, jank_factor)
    print(f'Processed {fbx_count} files from {input_folder}\\')
    log_file.close()


def process_file(import_path:str, d_mode:DistanceMode, fat_factor:float, jank_factor:float):
    print(f'Processing { import_path }...')
    bpy.ops.import_scene.fbx(filepath=import_path)
    bpy.ops.object.select_all(action='SELECT')
    process_selection(d_mode, fat_factor, jank_factor)
    output_path = str(import_path).replace("input", "output")
    bpy.ops.export_scene.fbx(filepath=output_path, path_mode='ABSOLUTE')
    bpy.ops.object.delete()


def process_selection(d_mode:DistanceMode, fat_factor:float, jank_factor:float):
    for target in bpy.context.selected_objects:
        # assign active object - necessary for blender to not throw error when entering EDIT mode
        bpy.context.view_layer.objects.active = target
        if fat_factor != 0:
            fatten(target, fat_factor)
        bpy.ops.object.transform_apply(scale=True, location=False, rotation=True)
        jankify(target, d_mode, jank_factor)


def fatten(target, fat_factor:float):
    # get the longest side
    longest = target.dimensions[0]
    if target.dimensions[1] > longest:
        longest = target.dimensions[1]
    if target.dimensions[2] > longest:
        longest = target.dimensions[2]
    # how much to fatten the item.
    fat_factor = longest * fat_factor
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.transform.shrink_fatten(value=fat_factor)
    bpy.ops.object.mode_set(mode='OBJECT')


def jankify(target, d_mode:DistanceMode, jank_factor:float, sphere_ratio:float=0.5, dist_ratio:float=0.5):
    # switch to EDIT mode - required for bmesh
    bpy.ops.object.mode_set(mode='EDIT')
    target_mesh = bmesh.from_edit_mesh(target.data)
    # necessary - https://blender.stackexchange.com/a/31750
    target_mesh.verts.ensure_lookup_table()

    neighbours = {}
    for vert in target_mesh.verts:
        neighbours[vert] = get_adjacent_vertices(vert)

    for vert in target_mesh.verts:
        count = 0
        total_dist = 0.0
        max_dist = None
        min_dist = None
        dist_vectors = []
        
        # collect data on neighbouring vertices
        for neighbour in neighbours[vert]:
            dist = distance_between_vectors(vert.co, neighbour)
            vec = vector_subtract(neighbour, vert.co)
            obj = {'dist': dist, 'vec': vec}
            dist_vectors.append(obj)
            if max_dist is None:
                max_dist = dist
            elif dist > max_dist:
                max_dist = dist
            if min_dist is None:
                min_dist = dist
            elif dist < min_dist:
                min_dist = dist
            total_dist += dist
            count += 1
            # print(f'original: {vert.co} \nneighbor: {neighbour}')
        # print("-----------------------")
        avg_dist = total_dist/count
        bias_vector = [0.0, 0.0, 0.0]
        
        # get a bias vector based on proximity of neighbouring vertices
        for obj in dist_vectors:
            weight = (1.0 - obj['dist']/max_dist)/count
            vec = vector_scale(vector_normalize(obj['vec']), weight)
            bias_vector = vector_subtract(bias_vector, vec)
        # generate random vector and skew the direction slightly toward the bias vector
        rand_vector = [random.random()*2.0 - 1.0 + bias_vector[0], random.random()
                       * 2.0 - 1.0 + bias_vector[1], random.random()*2.0 - 1.0 + bias_vector[2]]
        rand_vector = vector_normalize(rand_vector)
        rand_factor = random.random()
        # set distance factor to corresponding distance mode
        if d_mode == DistanceMode.AVG:
            dist_factor = avg_dist
        elif d_mode == DistanceMode.MIN:
            dist_factor = min_dist
        elif d_mode == DistanceMode.MAX:
            dist_factor = max_dist
        # scale the normalized vector based on desired jank factor and distance factor
        rand_length = rand_factor * jank_factor * dist_factor
        rand_vector = vector_scale(rand_vector, rand_factor * jank_factor * dist_factor)
        
        # check that the random vector doesn't extend too close to neighbouring vertices
        for neighbour in neighbours[vert]:
            vec_to_n = vector_subtract(neighbour, vert.co)
            angle = abs(angle_between_vectors(rand_vector, vec_to_n))
            # if neighbour vert is within 90deg of random vector
            if angle < math.pi/2.0:
                dist = vector_length(vec_to_n)
                sphere_radius = dist * sphere_ratio
                # if random vector intersects exclusion sphere around neighbour
                if math.sin(angle) * dist < sphere_radius:
                    sect_dist = find_intersect_distance(
                        sphere_radius, angle, dist)
                    if rand_length > sect_dist:
                        # recalculate length using exclusion sphere distance
                        rand_vector = vector_scale(
                            vector_normalize(rand_vector), sect_dist * rand_factor)
                else:
                    if rand_length > dist * dist_ratio:
                        # recalculate length using max distance ratio
                        rand_vector = vector_scale(
                            vector_normalize(rand_vector), dist * dist_ratio * rand_factor)
        vert.co = vector_add(vert.co, rand_vector)
    # de-select, to return to object mode
    bpy.ops.object.mode_set(mode='OBJECT')


# HELPERS

def find_intersect_distance(radius, angle, dist):
    l_opp = math.sin(angle) * dist
    l_adj_radius = math.sqrt(radius*radius - l_opp*l_opp)
    l_adj_dist = math.cos(angle) * dist
    return l_adj_dist - l_adj_radius


def angle_between_vectors(vec1, vec2):
    return math.acos((vec1[0]*vec2[0] + vec1[1]*vec2[1] + vec1[2]*vec2[2]) / (math.sqrt(vec1[0]*vec1[0] + vec1[1]*vec1[1] + vec1[2]*vec1[2]) * math.sqrt(vec2[0]*vec2[0] + vec2[1]*vec2[1] + vec2[2]*vec2[2])))


def distance_between_vectors(vec1, vec2):
    vec = vector_subtract(vec1, vec2)
    return vector_length(vec)


def vector_normalize(vec):
    l = vector_length(vec)
    return [vec[0]/l, vec[1]/l, vec[2]/l]


def vector_length(vec):
    return math.sqrt(vec[0]*vec[0] + vec[1]*vec[1] + vec[2]*vec[2])


def vector_scale(vec, scale):
    return [vec[0]*scale, vec[1]*scale, vec[2]*scale]


def vector_add(vec1, vec2):
    return [vec1[0] + vec2[0], vec1[1] + vec2[1], vec1[2] + vec2[2]]


def vector_subtract(vec1, vec2):
    return [vec1[0] - vec2[0], vec1[1] - vec2[1], vec1[2] - vec2[2]]


def get_adjacent_vertices(vert):
    # print(v.link_edges)
    adjacent = []
    for edge in vert.link_edges:
        v_other = edge.other_vert(vert)
        # print("%d -> %d via edge %d" % (v.index, v_other.index, e.index))
        adjacent.append(list(v_other.co))
    # print(f'adjacent: {adjacent}')
    return adjacent


# RUN
main(d_mode=0, fat_factor=2, jank_factor=0.15)