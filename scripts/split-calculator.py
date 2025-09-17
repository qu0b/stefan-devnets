#!/usr/bin/env python3
"""
Ethereum Node Distribution Calculator

This script calculates the distribution of validators and machines across
different client combinations and node types (default/full/super), satisfying
both validator and machine distribution constraints simultaneously.
"""

import numpy as np
from typing import Dict, List, Tuple, NamedTuple
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURATION
# ============================================================================

TOTAL_VALIDATORS = 15000
BASE_VALIDATORS_PER_MACHINE = 255

# Consensus Layer client distribution
CL_CLIENTS = {
    'prysm': 0.25,
    'lighthouse': 0.25,
    'teku': 0.20,
    'lodestar': 0.10,
    'nimbus': 0.10,
    'grandine': 0.10
}

# Execution Layer client distribution
EL_CLIENTS = {
    'geth': 0.45,
    'nethermind': 0.30,
    'ethereumjs': 0.01,
    'reth': 0.08,
    'besu': 0.08,
    'erigon': 0.07,
    'nimbusel': 0.01,
}

# Node type distributions
NODE_TYPES = ['default', 'full', 'super']

# Target distributions (must sum to 1.0)
VALIDATOR_DISTRIBUTION = {
    'default': 0.70,  # 70% of validators
    'full': 0.20,     # 20% of validators
    'super': 0.10     # 10% of validators
}

MACHINE_DISTRIBUTION = {
    'default': 0.80,  # 50% of machines
    'full': 0.15,     # 15% of machines
    'super': 0.05     # 05% of machines
}

# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class Allocation:
    """Represents a single node allocation."""
    cl_name: str
    el_name: str
    node_type: str
    validators: int
    machines: int

    @property
    def suffix(self):
        return '' if self.node_type == 'default' else f'_{self.node_type}'

    @property
    def variable_name(self):
        return f"{self.cl_name.lower()}_{self.el_name.lower()}{self.suffix}"

    @property
    def config_name(self):
        return f"{self.cl_name.lower()}-{self.el_name.lower()}{self.suffix.replace('_', '-')}"


# ============================================================================
# CORE ALGORITHM
# ============================================================================

def calculate_allocations() -> List[Allocation]:
    """
    Calculate optimal allocations using a cleaner approach.
    """
    allocations = []
    total_machines = TOTAL_VALIDATORS / BASE_VALIDATORS_PER_MACHINE

    # Calculate validators per machine for each type
    validators_per_machine = {}
    for node_type in NODE_TYPES:
        if MACHINE_DISTRIBUTION[node_type] > 0:
            validators_per_machine[node_type] = (
                (VALIDATOR_DISTRIBUTION[node_type] * TOTAL_VALIDATORS) /
                (MACHINE_DISTRIBUTION[node_type] * total_machines)
            )
        else:
            validators_per_machine[node_type] = 0

    # Create all allocations
    for cl_name, cl_pct in CL_CLIENTS.items():
        for el_name, el_pct in EL_CLIENTS.items():
            base_validators = TOTAL_VALIDATORS * cl_pct * el_pct
            base_machines = total_machines * cl_pct * el_pct

            for node_type in NODE_TYPES:
                validators = base_validators * VALIDATOR_DISTRIBUTION[node_type]
                machines = base_machines * MACHINE_DISTRIBUTION[node_type]

                allocations.append(Allocation(
                    cl_name=cl_name,
                    el_name=el_name,
                    node_type=node_type,
                    validators=validators,
                    machines=machines
                ))

    return allocations, validators_per_machine


def apply_intelligent_rounding(allocations: List[Allocation], total_machines: int) -> List[Allocation]:
    """
    Round machine counts while preserving distribution and ensuring all validators are allocated.
    """
    # Group by node type
    by_type = {'default': [], 'full': [], 'super': []}
    for alloc in allocations:
        by_type[alloc.node_type].append(alloc)

    rounded_allocations = []

    for node_type in NODE_TYPES:
        type_allocations = by_type[node_type]
        target_machines = round(total_machines * MACHINE_DISTRIBUTION[node_type])

        # Sort by machine count (descending) to prioritize larger allocations
        type_allocations.sort(key=lambda a: a.machines, reverse=True)

        # Calculate total validators for this type
        total_type_validators = sum(a.validators for a in type_allocations)

        # For small target machines, only allocate to the top combinations
        if target_machines <= 10:
            # Only give machines to the top allocations
            machine_assignments = []
            for i, alloc in enumerate(type_allocations):
                if i < target_machines:
                    # Give 1 machine to each of the top allocations
                    machine_assignments.append((alloc, 1))
                else:
                    # No machine for the rest
                    machine_assignments.append((alloc, 0))
        else:
            # Standard rounding for larger allocations
            machine_assignments = []
            total_assigned = 0

            for alloc in type_allocations:
                # Use fractional allocation
                ideal_machines = alloc.machines

                # For default nodes, be more generous with rounding
                if node_type == 'default':
                    if ideal_machines >= 0.4:
                        machines = max(1, round(ideal_machines))
                    else:
                        machines = 0
                else:
                    # For full/super, be more restrictive
                    if ideal_machines >= 0.7:
                        machines = max(1, round(ideal_machines))
                    else:
                        machines = 0

                machine_assignments.append((alloc, machines))
                total_assigned += machines

            # Adjust to meet target
            diff = target_machines - total_assigned

            if diff > 0:
                # Need more machines - add to largest allocations first
                for i in range(len(machine_assignments)):
                    if diff <= 0:
                        break
                    alloc, machines = machine_assignments[i]
                    if alloc.validators > 20 and machines == 0:
                        machine_assignments[i] = (alloc, 1)
                        diff -= 1

            elif diff < 0:
                # Have too many machines - remove from smallest allocations
                for i in range(len(machine_assignments) - 1, -1, -1):
                    if diff >= 0:
                        break
                    alloc, machines = machine_assignments[i]
                    if machines > 0 and alloc.validators < 50:
                        machine_assignments[i] = (alloc, 0)
                        diff += 1

        # Create final allocations, redistributing validators from zero-machine allocations
        orphaned_validators = 0
        final_type_allocations = []

        for alloc, machines in machine_assignments:
            if machines > 0:
                final_type_allocations.append(Allocation(
                    cl_name=alloc.cl_name,
                    el_name=alloc.el_name,
                    node_type=alloc.node_type,
                    validators=int(alloc.validators),
                    machines=machines
                ))
            else:
                orphaned_validators += int(alloc.validators)

        # Redistribute orphaned validators proportionally
        if orphaned_validators > 0 and final_type_allocations:
            validators_per_allocation = orphaned_validators / len(final_type_allocations)
            for alloc in final_type_allocations:
                alloc.validators += int(validators_per_allocation)
            # Handle remainder
            remainder = orphaned_validators - int(validators_per_allocation) * len(final_type_allocations)
            if remainder > 0:
                final_type_allocations[0].validators += remainder

        rounded_allocations.extend(final_type_allocations)

    return rounded_allocations


def generate_terraform_output(allocations: List[Allocation]) -> str:
    """Generate Terraform variable definitions."""
    # Sort allocations for consistent output
    allocations.sort(key=lambda a: (a.cl_name, a.el_name, a.node_type))

    output = []
    validator_start = 0

    for alloc in allocations:
        if alloc.machines == 0 or alloc.validators < 1:
            continue

        validator_end = validator_start + alloc.validators

        output.append(f'variable "{alloc.variable_name}" {{')
        output.append(f'  default = {{')
        output.append(f'    name            = "{alloc.config_name}"')
        output.append(f'    count           = {alloc.machines}')
        output.append(f'    validator_start = {validator_start}')
        output.append(f'    validator_end   = {validator_end}')
        output.append(f'  }}')
        output.append(f'}}')
        output.append('')

        validator_start = validator_end

    return '\n'.join(output)


def print_analysis(allocations: List[Allocation], validators_per_machine: Dict) -> int:
    """Print distribution analysis."""
    # Calculate totals by type
    by_type = {'default': [], 'full': [], 'super': []}
    for alloc in allocations:
        if alloc.machines > 0:
            by_type[alloc.node_type].append(alloc)

    validator_totals = {t: sum(a.validators for a in allocs) for t, allocs in by_type.items()}
    machine_totals = {t: sum(a.machines for a in allocs) for t, allocs in by_type.items()}

    total_validators = sum(validator_totals.values())
    total_machines = sum(machine_totals.values())

    print("# " + "=" * 70)
    print("# CONFIGURATION")
    print("# " + "=" * 70)
    print(f"# Total validators target: {TOTAL_VALIDATORS}")
    print(f"# Target validator distribution: ", end="")
    print(", ".join([f"{k}={v*100:.0f}%" for k, v in VALIDATOR_DISTRIBUTION.items()]))
    print(f"# Target machine distribution: ", end="")
    print(", ".join([f"{k}={v*100:.0f}%" for k, v in MACHINE_DISTRIBUTION.items()]))
    print()

    print("# Validators per machine by type (theoretical):")
    for node_type, vpm in validators_per_machine.items():
        print(f"#   {node_type}: {vpm:.0f} validators/machine")
    print()

    print("# " + "=" * 70)
    print("# RESULTS")
    print("# " + "=" * 70)
    print(f"# Total validators allocated: {total_validators}")
    print(f"# Total machines: {total_machines}")
    print()

    if total_validators > 0:
        print("# Actual validator distribution:")
        for node_type in NODE_TYPES:
            count = validator_totals.get(node_type, 0)
            pct = count / total_validators * 100 if total_validators > 0 else 0
            target = VALIDATOR_DISTRIBUTION[node_type] * 100
            diff = pct - target
            print(f"#   {node_type}: {count} ({pct:.1f}%) [target: {target:.0f}%, diff: {diff:+.1f}%]")

    if total_machines > 0:
        print()
        print("# Actual machine distribution:")
        for node_type in NODE_TYPES:
            count = machine_totals.get(node_type, 0)
            pct = count / total_machines * 100 if total_machines > 0 else 0
            target = MACHINE_DISTRIBUTION[node_type] * 100
            diff = pct - target
            print(f"#   {node_type}: {count} ({pct:.1f}%) [target: {target:.0f}%, diff: {diff:+.1f}%]")

    return total_validators


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main execution."""
    # Calculate initial allocations
    allocations, validators_per_machine = calculate_allocations()

    # Apply intelligent rounding
    total_machines = TOTAL_VALIDATORS / BASE_VALIDATORS_PER_MACHINE
    rounded_allocations = apply_intelligent_rounding(allocations, total_machines)

    # Print analysis
    total_allocated = print_analysis(rounded_allocations, validators_per_machine)
    print()

    # Generate terraform output
    terraform_output = generate_terraform_output(rounded_allocations)
    print(terraform_output)

    # Verify we allocated all validators
    if abs(total_allocated - TOTAL_VALIDATORS) > 10:
        print(f"\n# WARNING: Only allocated {total_allocated} validators out of {TOTAL_VALIDATORS}")


if __name__ == "__main__":
    main()
