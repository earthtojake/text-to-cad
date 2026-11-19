# URDF frames

Read this when a joint origin or an axis is written, or a link moves the wrong way. The frame
contract is in [SKILL.md](../SKILL.md#author-by-hand). These are the two places it is misread, and
no validator sees either.

- **Positive rotation is right-handed about the axis, whatever the joint is called.** With +X
  forward, +Y left and +Z up, a positive turn about +Y tips an upright link forward and a forward
  link down. A pitch joint that should raise a forward link for positive values takes
  `<axis xyz="0 -1 0"/>`. Write each joint's positive motion in the ledger
  ([urdf-ledger.md](urdf-ledger.md)) and sweep it ([urdf-checks.md](urdf-checks.md#the-sweep)).
- **The axis is in the joint frame, so the joint origin's `rpy` turns it.** `<axis xyz="0 0 1"/>`
  under `rpy="1.5708 0 0"` turns about the parent's -Y. Where the mechanism allows, leave joint
  origins unrotated and give each axis as a signed principal direction (`1 0 0`, `0 -1 0`): it then
  reads the same in the parent's frame. An axis that is not principal is a reason to check the
  frames again before accepting it.
