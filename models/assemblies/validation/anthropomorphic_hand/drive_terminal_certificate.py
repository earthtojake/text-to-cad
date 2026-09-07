"""Combine completed independent terminal checks without rerunning CAD."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    reports = {
        name: json.loads((HERE / filename).read_text())
        for name, filename in {
            'strict': 'drive_terminal_strict.json',
            'seating_release_mutual': 'drive_terminal_check.json',
            'motion': 'drive_terminal_motion_check.json',
            'end_release': 'drive_terminal_end_release.json',
        }.items()
    }
    strict, base, motion, release = (reports[k] for k in reports)
    assert strict['ok'] and strict['occurrenceCount'] == 336
    assert strict['selfIntersectionCheck'] == 'every-placement'
    assert len(base['seating']) == len(base['capstan_bond_seating']) == 48
    assert len(base['withdrawal']) == 200 and len(base['capture']) == 30
    assert base['pair_checks'] == 336 * 335 // 2
    assert not base['failures']
    assert motion['ok'] and not motion['partial'] and not motion['failures']
    assert len(set(motion['completed_routes'])) == 48
    assert len(motion['motion_seating']) == len(motion['hardware_motion']) == 434
    assert release['ok']
    result = {
        'ok': True,
        'occurrences': 336,
        'driven_occurrences': 288,
        'capstan_bond_occurrences': 48,
        'strict_every_placement': True,
        'neutral_driven_seatings': 48,
        'neutral_capstan_bond_seatings': 48,
        'neutral_mutual_pairs': base['pair_checks'],
        'five_family_capture_directions': len(base['capture']),
        'five_family_removal_steps': len(base['withdrawal']),
        'target_joint_poses': len(motion['motion_seating']),
        'hardware_poses': len(motion['hardware_motion']),
        'failures': [],
        'rope_retraction_mm': 0.85,
        'capstan_bond_standalone_release_certified': False,
        'capstan_explode_policy': 'Keep bonded resin, steel ferrule and capstan grouped.',
        'proof_files': [
            'drive_terminal_strict.json', 'drive_terminal_check.json',
            'drive_terminal_motion_check.json', 'drive_terminal_end_release.json',
        ],
        'scope': 'Exact local terminal seating, neutral mutual pairs, five-family removals and target-joint motion against real shaft/bushing hardware; whole-hand frame/guide collisions remain the integrator gate.',
    }
    (HERE / 'drive_terminal_certificate.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
