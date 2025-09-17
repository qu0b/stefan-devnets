#!/usr/bin/env python3
"""
Simplified Ethereum Node Distribution Calculator

Specify exact machine counts per node type, and the script distributes
validators and client combinations accordingly.
"""

import math
from dataclasses import dataclass
from typing import Dict, List

# ============================================================================
# CONFIGURATION
# ============================================================================

TOTAL_VALIDATORS = 15000

# Exact number of machines for each node type
MACHINE_COUNTS = {
    'default': 32,   # Standard nodes
    'full': 6,       # Full nodes
    'super': 2       # Super nodes
}

# Consensus Layer client distribution (must sum to 1.0)
CL_CLIENTS = {
    'prysm': 0.25,
    'lighthouse': 0.25,
    'teku': 0.20,
    'lodestar': 0.10,
    'nimbus': 0.10,
    'grandine': 0.10
}

# Execution Layer client distribution (must sum to 1.0)
EL_CLIENTS = {
    'geth': 0.50,
    'nethermind': 0.25,
    'ethereumjs': 0.01,
    'reth': 0.08,
    'besu': 0.08,
    'erigon': 0.07,
    'nimbusel': 0.01,
}

# Validator distribution across node types (must sum to 1.0)
VALIDATOR_DISTRIBUTION = {
    'default': 0.70,  # 70% of validators on default nodes
    'full': 0.20,     # 20% of validators on full nodes
    'super': 0.10     # 10% of validators on super nodes
}

# ============================================================================
# CORE LOGIC
# ============================================================================

@dataclass
class NodeAllocation:
    """Represents a single node configuration."""
    cl_name: str
    el_name: str
    node_type: str
    machines: int
    validators: int

    @property
    def variable_name(self):
        suffix = '' if self.node_type == 'default' else f'_{self.node_type}'
        return f"{self.cl_name.lower()}_{self.el_name.lower()}{suffix}"

    @property
    def config_name(self):
        suffix = '' if self.node_type == 'default' else f'-{self.node_type}'
        return f"{self.cl_name.lower()}-{self.el_name.lower()}{suffix}"


def calculate_allocations() -> List[NodeAllocation]:
    """
    Calculate node allocations based on fixed machine counts.
    """
    allocations = []

    # Calculate validators per node type
    validators_by_type = {
        node_type: int(TOTAL_VALIDATORS * VALIDATOR_DISTRIBUTION[node_type])
        for node_type in VALIDATOR_DISTRIBUTION
    }

    # Calculate validators per machine for each type
    validators_per_machine = {
        node_type: validators_by_type[node_type] / MACHINE_COUNTS[node_type]
        if MACHINE_COUNTS[node_type] > 0 else 0
        for node_type in MACHINE_COUNTS
    }

    # For each node type, distribute machines across client combinations
    for node_type in MACHINE_COUNTS:
        type_machines = MACHINE_COUNTS[node_type]
        type_validators = validators_by_type[node_type]

        if type_machines == 0:
            continue

        # Calculate how many machines each combination should get
        combination_machines = {}
        for cl_name, cl_pct in CL_CLIENTS.items():
            for el_name, el_pct in EL_CLIENTS.items():
                combination_weight = cl_pct * el_pct
                ideal_machines = type_machines * combination_weight
                combination_machines[(cl_name, el_name)] = ideal_machines

        # Sort combinations by ideal machine count (descending)
        sorted_combinations = sorted(
            combination_machines.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Allocate machines using "largest remainder" method
        allocated_machines = {}
        total_allocated = 0

        # First pass: allocate floor values
        for (cl, el), ideal in sorted_combinations:
            floor_machines = int(ideal)
            allocated_machines[(cl, el)] = floor_machines
            total_allocated += floor_machines

        # Second pass: distribute remaining machines by largest remainder
        remaining = type_machines - total_allocated
        if remaining > 0:
            remainders = [
                ((cl, el), ideal - int(ideal))
                for (cl, el), ideal in sorted_combinations
            ]
            remainders.sort(key=lambda x: x[1], reverse=True)

            for i in range(remaining):
                if i < len(remainders):
                    (cl, el), _ = remainders[i]
                    allocated_machines[(cl, el)] += 1

        # Create allocations with proportional validators
        for (cl, el), machines in allocated_machines.items():
            if machines > 0:
                # Validators for this allocation
                combination_weight = CL_CLIENTS[cl] * EL_CLIENTS[el]
                validators = int(type_validators * combination_weight)

                allocations.append(NodeAllocation(
                    cl_name=cl,
                    el_name=el,
                    node_type=node_type,
                    machines=machines,
                    validators=validators
                ))

    return allocations


def optimize_validator_distribution(allocations: List[NodeAllocation]) -> List[NodeAllocation]:
    """
    Adjust validator counts to ensure all validators are allocated.
    """
    # Group by node type
    by_type = {'default': [], 'full': [], 'super': []}
    for alloc in allocations:
        by_type[alloc.node_type].append(alloc)

    # Adjust validators for each type to match target exactly
    for node_type, type_allocations in by_type.items():
        if not type_allocations:
            continue

        target_validators = int(TOTAL_VALIDATORS * VALIDATOR_DISTRIBUTION[node_type])
        current_validators = sum(a.validators for a in type_allocations)

        if current_validators != target_validators:
            # Distribute the difference proportionally by machine count
            diff = target_validators - current_validators
            total_machines = sum(a.machines for a in type_allocations)

            for alloc in type_allocations:
                adjustment = round(diff * (alloc.machines / total_machines))
                alloc.validators += adjustment

            # Handle any remaining difference on the largest allocation
            current_validators = sum(a.validators for a in type_allocations)
            final_diff = target_validators - current_validators
            if final_diff != 0:
                largest = max(type_allocations, key=lambda a: a.machines)
                largest.validators += final_diff

    return allocations


def generate_output(allocations: List[NodeAllocation]) -> str:
    """Generate Terraform-style output."""
    # Sort for consistent output
    allocations.sort(key=lambda a: (a.cl_name, a.el_name, a.node_type))

    lines = []
    validator_start = 0

    for alloc in allocations:
        if alloc.machines == 0 or alloc.validators <= 0:
            continue

        validator_end = validator_start + alloc.validators

        lines.append(f'variable "{alloc.variable_name}" {{')
        lines.append(f'  default = {{')
        lines.append(f'    name            = "{alloc.config_name}"')
        lines.append(f'    count           = {alloc.machines}')
        lines.append(f'    validator_start = {validator_start}')
        lines.append(f'    validator_end   = {validator_end}')
        lines.append(f'  }}')
        lines.append(f'}}')
        lines.append('')

        validator_start = validator_end

    return '\n'.join(lines)


def print_summary(allocations: List[NodeAllocation]):
    """Print configuration and results summary."""
    total_machines = sum(MACHINE_COUNTS.values())

    print("# " + "=" * 70)
    print("# CONFIGURATION")
    print("# " + "=" * 70)
    print(f"# Total validators: {TOTAL_VALIDATORS}")
    print(f"# Total machines: {total_machines}")
    print()

    print("# Machine allocation (fixed):")
    for node_type, count in MACHINE_COUNTS.items():
        pct = count / total_machines * 100 if total_machines > 0 else 0
        print(f"#   {node_type}: {count} machines ({pct:.1f}%)")

    print()
    print("# Target validator distribution:")
    for node_type, pct in VALIDATOR_DISTRIBUTION.items():
        count = int(TOTAL_VALIDATORS * pct)
        print(f"#   {node_type}: {count} validators ({pct*100:.0f}%)")

    # Calculate actual results
    by_type = {'default': [], 'full': [], 'super': []}
    for alloc in allocations:
        by_type[alloc.node_type].append(alloc)

    print()
    print("# " + "=" * 70)
    print("# RESULTS")
    print("# " + "=" * 70)

    total_validators_allocated = sum(a.validators for a in allocations)
    total_machines_allocated = sum(a.machines for a in allocations)

    print(f"# Total validators allocated: {total_validators_allocated}")
    print(f"# Total machines allocated: {total_machines_allocated}")

    print()
    print("# Validators per machine by type:")
    for node_type, type_allocs in by_type.items():
        if type_allocs:
            total_v = sum(a.validators for a in type_allocs)
            total_m = sum(a.machines for a in type_allocs)
            vpm = total_v / total_m if total_m > 0 else 0
            print(f"#   {node_type}: {vpm:.0f} validators/machine")

    print()
    print("# Actual distribution:")
    for node_type, type_allocs in by_type.items():
        v_count = sum(a.validators for a in type_allocs)
        m_count = sum(a.machines for a in type_allocs)
        v_pct = v_count / total_validators_allocated * 100 if total_validators_allocated > 0 else 0
        m_pct = m_count / total_machines_allocated * 100 if total_machines_allocated > 0 else 0
        print(f"#   {node_type}: {m_count} machines, {v_count} validators ({v_pct:.1f}%)")

    print()
    print("# Client combination counts:")
    combination_machines = {}
    for alloc in allocations:
        key = f"{alloc.cl_name}-{alloc.el_name}"
        if key not in combination_machines:
            combination_machines[key] = {'default': 0, 'full': 0, 'super': 0}
        combination_machines[key][alloc.node_type] = alloc.machines

    for combo, counts in sorted(combination_machines.items()):
        total = sum(counts.values())
        if total > 0:
            print(f"#   {combo}: {total} total (default={counts['default']}, full={counts['full']}, super={counts['super']})")


def main():
    """Main execution."""
    # Calculate initial allocations
    allocations = calculate_allocations()

    # Optimize validator distribution
    allocations = optimize_validator_distribution(allocations)

    # Print summary
    print_summary(allocations)
    print()

    # Generate output
    output = generate_output(allocations)
    print(output)


if __name__ == "__main__":
    main()