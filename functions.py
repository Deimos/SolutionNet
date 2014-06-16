from cgi import escape
from collections import defaultdict

from boto.ses import SESConnection


def first_nonzero_index(input_list):
    for i, item in enumerate(input_list):
        if item != 0:
            return i
    return -1


def last_nonzero_index(input_list):
    reversed_list = input_list[::-1]
    index = first_nonzero_index(reversed_list)
    if index == -1:
        return -1
    else:
        return len(input_list) - index


def calculate_mean(data, start, step_size):
    total = 0
    for i, item in enumerate(data):
        total += ((start + i) * step_size + (step_size / 2)) * item
    return round(float(total) / float(sum(data)), 2)


def process_chart_data(data, output, prefix):
    start = data[0]
    end = data[1]
    step_size = data[2]
    data = data[6:]
    first_nonzero = first_nonzero_index(data)
    last_nonzero = last_nonzero_index(data)

    output[prefix+'_data'] = ','.join(map(str, data[first_nonzero:last_nonzero+1]))
    output[prefix+'_labels'] = str()
    for item in range(first_nonzero * step_size + start, last_nonzero * step_size + 1, step_size):
        output[prefix+'_labels'] += "'"+str(item)
        if (step_size > 1):
            output[prefix+'_labels'] += '-' + str(item + (step_size - 1))
        output[prefix+'_labels'] += "',"
    output[prefix+'_labels'] = output[prefix+'_labels'][:-1]
    output[prefix+'_mean'] = calculate_mean(data, start, step_size)


def ses_email(config, to_address, subject, body):
    connection = SESConnection(aws_access_key_id=config['AWS_ACCESS_KEY_ID'],
                               aws_secret_access_key=config['AWS_SECRET_ACCESS_KEY_ID'])
    from_address = '"SolutionNet" <{0}>'.format(config['FROM_EMAIL_ADDRESS'])

    connection.send_email(from_address,
                          str(subject),
                          str(escape(body)),
                          str(to_address))


def process_solution(solution):
    reactors = []
    path = {}

    # for each reactor, create a 10x8 2D dict of "cells"
    # each cell is a list of tuples, representing type, color/class, and optional text (for sensors) for each member in the cell
    for component in solution.components:
        if "reactor" in component.type:
            cells = {}
            path = {}
            paths_to_process = []
            for path_color in ('blue', 'red'):
                path[path_color] = {}
            for y in range(0, 8):
                for x in range(0, 10):
                    cells[(x, y)] = []
                    for path_color in ('blue', 'red'):
                        path[path_color][(x, y)] = {}
                        path[path_color][(x, y)]['edges'] = set()
                        path[path_color][(x, y)]['entry_edges'] = set()
                        path[path_color][(x, y)]['dir_change'] = ''

            # add all the instructions to the cell grid
            for member in component.members:
                # take note of any instructions that start a path, for path-building later
                if member.type in ('instr-start', 'instr-toggle', 'instr-sensor', 'instr-control'):
                    new_path = {}
                    new_path['start_type'] = member.type
                    new_path['start_pos'] = (member.x, member.y)
                    new_path['start_dir'] = member.ARROW_DIRS[member.arrow_dir]
                    new_path['color'] = member.color
                    paths_to_process.append(new_path)

                # take note of any direction changes (arrow)
                if member.type == 'instr-arrow':
                    path[member.color][(member.x, member.y)]['dir_change'] = member.ARROW_DIRS[member.arrow_dir]

                # set up the class to give to img and div tags, color unless it's a directional
                if member.type == 'instr-arrow':
                    member_class = member.color+'-arrow'
                elif member.type in ('instr-start', 'instr-toggle', 'instr-sensor', 'instr-control'):
                    member_class = member.color+" "+member.ARROW_DIRS[member.arrow_dir]
                else:
                    member_class = member.color

                # if it's a fuser/splitter, we need to add the other half to the cell to the right as well
                if member.type in ('feature-fuser', 'feature-splitter') and member.x < 9:
                    cells[(member.x+1, member.y)].append((member.image_name.replace('.png', '2.png'), member_class))

                if member.type == 'instr-sensor':
                    cells[(member.x, member.y)].append((member.image_name, member_class, member.element))
                else:
                    cells[(member.x, member.y)].append((member.image_name, member_class))

            # build the paths
            OPPOSITE_SIDE = {"l": "r",
                             "r": "l",
                             "u": "d",
                             "d": "u"}
            while len(paths_to_process) > 0:
                current_path = paths_to_process.pop(0)
                current_pos = list(current_path['start_pos'])
                # arrows in the same cell as a start instruction override its direction
                if current_path['start_type'] == 'instr-start':
                    current_dir = path[current_path['color']][tuple(current_pos)]['dir_change'] or current_path['start_dir']
                else:
                    current_dir = current_path['start_dir']
                path[current_path['color']][tuple(current_pos)]['edges'].add(current_dir)
                while True:
                    # move position
                    if current_dir == 'l':
                        current_pos[0] -= 1
                    elif current_dir == 'r':
                        current_pos[0] += 1
                    elif current_dir == 'u':
                        current_pos[1] -= 1
                    elif current_dir == 'd':
                        current_pos[1] += 1

                    # if we're now outside the graph, stop
                    if not (0 <= current_pos[0] <= 9 and 0 <= current_pos[1] <= 7):
                        break

                    # if we've already come into this cell from this direction, stop
                    if OPPOSITE_SIDE[current_dir] in path[current_path['color']][tuple(current_pos)]['entry_edges']:
                        break

                    # otherwise, mark the incoming edge
                    path[current_path['color']][tuple(current_pos)]['edges'].add(OPPOSITE_SIDE[current_dir])
                    path[current_path['color']][tuple(current_pos)]['entry_edges'].add(OPPOSITE_SIDE[current_dir])

                    # determine if we're changing direction or going straight through
                    if path[current_path['color']][tuple(current_pos)]['dir_change']:
                        current_dir = path[current_path['color']][tuple(current_pos)]['dir_change']

                    # mark outgoing edge
                    path[current_path['color']][tuple(current_pos)]['edges'].add(current_dir)

            reactors.append((cells, path, component.type))

    return reactors


def process_overview(solution):
    def add_component(cells, type, start_x, start_y):
        size_x = COMPONENT_SIZES[type][0]
        size_y = COMPONENT_SIZES[type][1]

        if start_x < 0:
            size_x += start_x
            start_x = 0
        if start_y < 0:
            size_y += start_y
            start_y = 0

        cells[(start_x, start_y)] += ['component', type, size_x, size_y, COMPONENT_LABELS[type]]
        for x in range(0, size_x):
            for y in range(0, size_y):
                if x != 0 or y != 0:
                    cells[(start_x + x, start_y + y)].append('skip')

    COMPONENT_SIZES = {"drag-silo-input": (5, 5),
                       "drag-oceanic-input": (2, 2),
                       "drag-atmospheric-input": (2, 2),
                       "drag-mining-input": (3, 2),
                       "drag-storage-tank": (3, 3),
                       "drag-spaceship-input": (2, 3),
                       "drag-powerplant-input": (14, 15),
                       "cargo-freighter": (2, 3),
                       "oxygen-tank": (3, 3),
                       "recycler": (5, 5),
                       "control-center": (3, 3),
                       "particle-accelerator": (3, 3),
                       "rocket-launch-pad": (3, 3),
                       "hydrogen-laser": (5, 5),
                       "chemical-laser": (3, 3),
                       "ancient-pump": (2, 2),
                       "omega-missile-launcher": (3, 3),
                       "thruster-controls": (3, 6),
                       "teleporter-in": (3, 1),
                       "teleporter-out": (3, 1),
                       "internal-storage-tank": (2, 3),
                       "crash-canister": (4, 4)}

    COMPONENT_LABELS = {"drag-silo-input": "input",
                        "drag-oceanic-input": "input",
                        "drag-atmospheric-input": "input",
                        "drag-spaceship-input": "input",
                        "drag-mining-input": "input",
                        "drag-storage-tank": "storage tank",
                        "drag-powerplant-input": "input",
                        "cargo-freighter": "cargo output",
                        "oxygen-tank": "oxygen tank",
                        "recycler": "recycler",
                        "control-center": "control center",
                        "particle-accelerator": "particle accelerator",
                        "rocket-launch-pad": "rocket launch pad",
                        "hydrogen-laser": "hydrogen laser",
                        "chemical-laser": "chemical laser",
                        "ancient-pump": "input",
                        "omega-missile-launcher": "omega missile launcher",
                        "thruster-controls": "thruster controls",
                        "teleporter-in": "teleporter in",
                        "teleporter-out": "teleporter out",
                        "internal-storage-tank": "tank output",
                        "crash-canister": "crash canister"}

    PIPE_COLORS = ['#fefe33', '#8601af',
                   '#FB9902', '#0247FE',
                   '#FE2712', '#66B032',
                   '#FABC02', '#3D01A4',
                   '#FD5308', '#0392CE',
                   '#A7194B', '#D0EA2B']

    cells = defaultdict(list)
    reactor_num = 1
    component_num = 1
    component_nums = {}

    for component in solution.components:
        base_x = component.x
        base_y = component.y
        component_nums[component.component_id] = component_num
        component_num += 1

        if component.type.endswith('-reactor'):
            cells[(base_x, base_y)] += ['reactor', reactor_num]
            reactor_num += 1
            for x in range(0, 4):
                for y in range(0, 4):
                    if x != 0 or y != 0:
                        cells[(base_x + x, base_y + y)].append('skip')
        elif component.type in COMPONENT_SIZES:
            add_component(cells, component.type, base_x, base_y)
        else:
            cells[(base_x, base_y)] += ['unknown', component.type]

        for pipe in component.pipes:
            pipe_color = PIPE_COLORS[((component_nums[pipe.component_id] - 1) * 2) % 6 + pipe.output_id]

            # if the cell already has a pipe in it
            if cells[(base_x + pipe.x, base_y + pipe.y)]:
                cells[(base_x + pipe.x, base_y + pipe.y)] += [pipe_color]
            else:
                cells[(base_x + pipe.x, base_y + pipe.y)] += ['pipe', pipe_color]

    # add "fixed" components if they're not already there
    for component in solution.level.fixedcomponents:
        add_component(cells, component.type, component.x, component.y)

    return cells
