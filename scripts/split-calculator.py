import numpy as np
import math

total_validators = 10000
base_validator_per_machine = 250  # Base reference

cl_split = {
    'prysm': 0.25,
    'lighthouse': 0.25,
    'teku': 0.20,
    'lodestar': 0.10,
    'nimbus': 0.10,
    'grandine': 0.10
}

el_split = {
    'geth': 0.50,
    'nethermind': 0.25,
    'ethereumjs': 0.01,
    'reth': 0.08,
    'besu': 0.08,
    'erigon': 0.07,
    'nimbusel': 0.01,
}

# Define BOTH validator and machine distributions
validator_distribution = {
    'default': 0.70,  # 70% of validators on default nodes
    'full': 0.20,     # 20% of validators on full nodes
    'super': 0.10     # 10% of validators on super nodes
}

machine_distribution = {
    'default': 0.50,  # 50% of machines are default nodes
    'full': 0.25,     # 25% of machines are full nodes
    'super': 0.25     # 25% of machines are super nodes
}

# Calculate validators per machine for each node type to satisfy both constraints
total_machines_estimate = total_validators / base_validator_per_machine

# Calculate actual validators per machine for each type
validators_per_machine_by_type = {}
for node_type in validator_distribution:
    if machine_distribution[node_type] > 0:
        validators_per_machine_by_type[node_type] = (
            (validator_distribution[node_type] * total_validators) /
            (machine_distribution[node_type] * total_machines_estimate)
        )
    else:
        validators_per_machine_by_type[node_type] = 0

print(f"# Configuration:")
print(f"# Total validators: {total_validators}")
print(f"# Validator distribution: default={validator_distribution['default']*100:.0f}%, full={validator_distribution['full']*100:.0f}%, super={validator_distribution['super']*100:.0f}%")
print(f"# Machine distribution: default={machine_distribution['default']*100:.0f}%, full={machine_distribution['full']*100:.0f}%, super={machine_distribution['super']*100:.0f}%")
print(f"# Validators per machine by type:")
for node_type, vpm in validators_per_machine_by_type.items():
    print(f"#   {node_type}: {vpm:.0f} validators/machine")
print()

# First pass: Calculate raw allocations
pairwise_allocations = {}
for cl_name, cl_percent in cl_split.items():
    for el_name, el_percent in el_split.items():
        pair_total_validators = total_validators * cl_percent * el_percent

        for node_type in validator_distribution:
            validators = pair_total_validators * validator_distribution[node_type]

            # Calculate machines needed for this validator count
            if validators_per_machine_by_type[node_type] > 0:
                machines_needed = validators / validators_per_machine_by_type[node_type]
            else:
                machines_needed = 0

            if node_type == 'default':
                key = (cl_name, el_name, '')
            else:
                key = (cl_name, el_name, f'_{node_type}')

            pairwise_allocations[key] = {
                'validators': validators,
                'machines_raw': machines_needed,
                'node_type': node_type
            }

# Second pass: Round machines intelligently to maintain distribution
# Group by node type
by_node_type = {'default': [], 'full': [], 'super': []}
for key, alloc in pairwise_allocations.items():
    by_node_type[alloc['node_type']].append((key, alloc))

# Round and adjust to maintain target distribution
final_allocations = {}
for node_type, allocations in by_node_type.items():
    # Sort by machines_raw descending to prioritize larger allocations
    sorted_allocs = sorted(allocations, key=lambda x: x[1]['machines_raw'], reverse=True)

    # Calculate target total machines for this type
    target_machines = round(total_machines_estimate * machine_distribution[node_type])

    # First, round all allocations
    machine_assignments = []
    total_assigned = 0

    for key, alloc in sorted_allocs:
        if alloc['machines_raw'] >= 0.5:  # Only create a machine if at least 0.5
            machines = max(1, round(alloc['machines_raw']))
        else:
            machines = 0
        machine_assignments.append((key, machines))
        total_assigned += machines

    # Adjust to meet target (simple adjustment - could be more sophisticated)
    diff = target_machines - total_assigned

    # If we need more machines, add to largest allocations
    if diff > 0:
        for i in range(min(diff, len(machine_assignments))):
            if machine_assignments[i][1] > 0:  # Only adjust existing allocations
                machine_assignments[i] = (machine_assignments[i][0], machine_assignments[i][1] + 1)

    # If we have too many machines, reduce from smallest non-zero allocations
    elif diff < 0:
        for i in range(len(machine_assignments) - 1, -1, -1):
            if diff >= 0:
                break
            if machine_assignments[i][1] > 1:  # Keep at least 1 machine
                reduction = min(machine_assignments[i][1] - 1, -diff)
                machine_assignments[i] = (machine_assignments[i][0], machine_assignments[i][1] - reduction)
                diff += reduction

    # Store final allocations
    for key, machines in machine_assignments:
        orig_alloc = dict([(k, a) for k, a in sorted_allocs if k == key][0][1])
        final_allocations[key] = {
            'validators': orig_alloc['validators'],
            'machines': machines,
            'node_type': node_type
        }

# Generate output
start = 0
output = ""
total_machines_actual = 0

# Sort by key to ensure consistent ordering
for key in sorted(final_allocations.keys()):
    allocation = final_allocations[key]
    cl, el, suffix = key

    validators = allocation['validators']
    machines = allocation['machines']

    if machines == 0:  # Skip if no machines allocated
        continue

    # Calculate actual validators for this allocation
    # Distribute validators proportionally based on machine count
    actual_validators = int(validators)

    if actual_validators < 1:  # Skip if less than 1 validator
        continue

    variable_name = f"{cl.lower()}_{el.lower()}{suffix}"
    name = f"{cl.lower()}-{el.lower()}{suffix.replace('_', '-')}"

    total_machines_actual += machines
    end = start + actual_validators

    output += f'variable "{variable_name}" {{\n'
    output += f'  default = {{\n'
    output += f'    name            = "{name}"\n'
    output += f'    count           = {machines}\n'
    output += f'    validator_start = {start}\n'
    output += f'    validator_end   = {end}\n'
    output += f'  }}\n'
    output += f'}}\n\n'

    start = end

# Calculate actual distributions
default_validators = 0
full_validators = 0
super_validators = 0
default_machines = 0
full_machines = 0
super_machines = 0

for key, allocation in final_allocations.items():
    if allocation['machines'] > 0:
        validators = int(allocation['validators'])
        machines = allocation['machines']

        cl, el, suffix = key
        if suffix == '':
            default_validators += validators
            default_machines += machines
        elif suffix == '_full':
            full_validators += validators
            full_machines += machines
        elif suffix == '_super':
            super_validators += validators
            super_machines += machines

print(output)
print(f"# Total validators allocated: {start}")
print(f"# Total machines: {total_machines_actual}")
print()
print(f"# Actual distribution:")
if start > 0:
    print(f"# Validators: default={default_validators} ({default_validators/start*100:.1f}%), "
          f"full={full_validators} ({full_validators/start*100:.1f}%), "
          f"super={super_validators} ({super_validators/start*100:.1f}%)")
if total_machines_actual > 0:
    print(f"# Machines: default={default_machines} ({default_machines/total_machines_actual*100:.1f}%), "
          f"full={full_machines} ({full_machines/total_machines_actual*100:.1f}%), "
          f"super={super_machines} ({super_machines/total_machines_actual*100:.1f}%)")