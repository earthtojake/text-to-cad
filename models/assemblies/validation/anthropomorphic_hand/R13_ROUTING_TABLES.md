# R13 routing and static evidence

24 axes, 48 antagonistic tendons and 48 independent actuators; 225 frozen static poses.

**Static mechanical verification passes. The model remains unfinished.** All 3259 native occurrences pass strict every-placement validation. All 225 poses pass hand-frame rigid, physically actuated rigid, tendon/rigid, curve/spacing and payout checks. Independent visual acceptance, choreography, explode and final Viewer handoff remain open.

The [export QA certificate](native_r13_export_fidelity_gate.json) preserves completed native material-difference proofs, fresh direct checks of 47 exported rigid bodies and complete native boundary-record comparisons for 46 variable tendons. The latter agree at 1e-10 in stored field units; that is not a global spatial-error bound. The failed exact Boolean identity diagnostic remains recorded separately.

## Tendon table

Lengths include the stored capstan wrap at neutral. Extrema cover all 225 static packets. Dimensions are millimeters unless stated.

| Tendon | Neutral length | Minimum radius | Maximum payout, rad | Maximum rope-length residual |
|---|---:|---:|---:|---:|
| thumb_cmc_abduction_positive | 471.364734 | 3.799823 | 3.284403302 | 1.71e-13 |
| thumb_cmc_abduction_negative | 456.912233 | 3.799995 | 3.822232119 | 1.71e-13 |
| thumb_cmc_flexion_positive | 434.581854 | 3.649222 | 1.637132277 | 2.5e-12 |
| thumb_cmc_flexion_negative | 430.685457 | 3.647935 | 1.947913358 | 2.5e-12 |
| thumb_mcp_abduction_positive | 432.094974 | 3.548821 | 3.218899510 | 1.02e-12 |
| thumb_mcp_abduction_negative | 429.616818 | 3.548368 | 2.100295513 | 1.93e-12 |
| thumb_mcp_flexion_positive | 388.655837 | 3.548256 | 3.349968031 | 5.12e-13 |
| thumb_mcp_flexion_negative | 385.909471 | 3.548011 | 2.021069506 | 1.99e-12 |
| thumb_ip_positive | 370.970630 | 3.500000 | 3.198443493 | 1.71e-13 |
| thumb_ip_negative | 370.196186 | 3.500000 | 1.788915493 | 8.53e-13 |
| index_mcp_abduction_positive | 314.017897 | 3.799753 | 5.160674292 | 5.68e-14 |
| index_mcp_abduction_negative | 307.902481 | 5.500000 | 4.010346457 | 1.65e-12 |
| index_mcp_flexion_positive | 522.670978 | 3.727919 | 5.975815839 | 3.41e-13 |
| index_mcp_flexion_negative | 518.043638 | 3.727919 | 4.432197079 | 1.14e-13 |
| index_pip_positive | 523.516309 | 3.645898 | 5.739701177 | 1.14e-13 |
| index_pip_negative | 519.673369 | 3.645898 | 4.162439391 | 1.14e-13 |
| index_dip_positive | 510.322768 | 3.500000 | 5.581770507 | 1.02e-12 |
| index_dip_negative | 508.146382 | 3.500000 | 4.002234325 | 1.02e-12 |
| middle_mcp_abduction_positive | 397.228832 | 5.500000 | 5.276874371 | 1.14e-13 |
| middle_mcp_abduction_negative | 388.779270 | 5.500000 | 4.252254553 | 2.27e-13 |
| middle_mcp_flexion_positive | 352.049837 | 4.007917 | 5.397162011 | 1.71e-13 |
| middle_mcp_flexion_negative | 354.824771 | 4.007917 | 4.041613439 | 9.66e-13 |
| middle_pip_positive | 356.605391 | 3.645898 | 5.173703645 | 5.68e-14 |
| middle_pip_negative | 361.255281 | 3.645898 | 3.804024059 | 7.96e-13 |
| middle_dip_positive | 602.324597 | 3.500000 | 5.900763525 | 1.14e-12 |
| middle_dip_negative | 598.454824 | 3.500000 | 4.286890660 | 1.02e-12 |
| ring_mcp_abduction_positive | 480.023958 | 5.500000 | 5.476505073 | 1.71e-13 |
| ring_mcp_abduction_negative | 465.947426 | 5.500000 | 4.383891631 | 1.71e-13 |
| ring_mcp_flexion_positive | 432.571193 | 4.007917 | 5.666186956 | 1.14e-13 |
| ring_mcp_flexion_negative | 431.760919 | 4.007917 | 4.220004537 | 1.71e-13 |
| ring_pip_positive | 432.098838 | 3.645898 | 5.414284619 | 2.27e-13 |
| ring_pip_negative | 433.741802 | 3.645898 | 3.990969912 | 2.27e-13 |
| ring_dip_positive | 418.973531 | 3.500000 | 5.189915748 | 9.09e-13 |
| ring_dip_negative | 423.416647 | 3.500000 | 3.785209594 | 9.66e-13 |
| little_mcp_abduction_positive | 313.817490 | 3.649839 | 3.616075981 | 5.68e-14 |
| little_mcp_abduction_negative | 300.338236 | 3.648006 | 3.258532428 | 5.12e-13 |
| little_mcp_flexion_positive | 523.533449 | 3.647669 | 3.671561139 | 7.96e-13 |
| little_mcp_flexion_negative | 519.342307 | 3.647669 | 2.914354069 | 3.41e-13 |
| little_pip_positive | 509.470817 | 3.645898 | 4.540271637 | 1.71e-13 |
| little_pip_negative | 508.249742 | 3.645898 | 3.403578398 | 1.71e-13 |
| little_dip_positive | 492.161876 | 3.500000 | 4.535639952 | 1.71e-13 |
| little_dip_negative | 493.585657 | 3.500000 | 3.427565883 | 1.14e-13 |
| wrist_abduction_positive | 346.173503 | 3.799824 | 0.551800562 | 5.68e-14 |
| wrist_abduction_negative | 334.443308 | 3.799956 | 0.551739689 | 5.68e-14 |
| wrist_flexion_positive | 281.802080 | 3.799879 | 1.652264597 | 5.68e-14 |
| wrist_flexion_negative | 443.982958 | 3.799725 | 5.382575275 | 1.14e-13 |
| palm_cup_positive | 287.590483 | 3.799681 | 3.480826691 | 1.14e-13 |
| palm_cup_negative | 294.118537 | 3.799681 | 2.937623892 | 1.14e-13 |

## Neutral moment arms

Finite differences check all 48 hand-side routes against each axis. Wrist transport compensation is separate. The JSON retains all 1152 matrix entries; this table shows both driven routes and the largest unintended coupling.

| Joint | Positive, mm | Negative, mm | Maximum unintended coupling, mm |
|---|---:|---:|---:|
| wrist_abduction | 11.000000 | -11.000000 | 8.14e-10 |
| wrist_flexion | 11.000000 | -11.000000 | 4.07e-10 |
| palm_cup | 7.000000 | -7.000000 | 8.14e-10 |
| index_mcp_abduction | 5.500000 | -5.500000 | 1.63e-09 |
| index_mcp_flexion | 5.500000 | -5.500000 | 4.07e-10 |
| index_pip | 4.500000 | -4.500000 | 1.63e-09 |
| index_dip | 3.500000 | -3.500000 | 0 |
| middle_mcp_abduction | 5.500000 | -5.500000 | 1.63e-09 |
| middle_mcp_flexion | 5.500000 | -5.500000 | 8.14e-10 |
| middle_pip | 4.500000 | -4.500000 | 0 |
| middle_dip | 3.500000 | -3.500000 | 0 |
| ring_mcp_abduction | 5.500000 | -5.500000 | 2.04e-09 |
| ring_mcp_flexion | 5.500000 | -5.500000 | 8.14e-10 |
| ring_pip | 4.500000 | -4.500000 | 8.14e-10 |
| ring_dip | 3.500000 | -3.500000 | 0 |
| little_mcp_abduction | 5.500000 | -5.500000 | 1.63e-09 |
| little_mcp_flexion | 5.500000 | -5.500000 | 8.14e-10 |
| little_pip | 4.500000 | -4.500000 | 1.63e-09 |
| little_dip | 3.500000 | -3.500000 | 0 |
| thumb_cmc_abduction | 7.000000 | -7.000000 | 4.07e-10 |
| thumb_cmc_flexion | 7.000000 | -7.000000 | 4.07e-10 |
| thumb_mcp_abduction | 5.500000 | -5.500000 | 8.14e-10 |
| thumb_mcp_flexion | 5.500000 | -5.500000 | 8.14e-10 |
| thumb_ip | 3.500000 | -3.500000 | 0 |

## Static samples

Every row passes curve/spacing, hand-frame rigid, physically actuated rigid, tendon/rigid and actuator payout checks. Unsampled transitions remain outside this static certificate.

| Sample | Pose in degrees | Completed checks |
|---|---|---|
| anatomical_fist | index_mcp_abduction=-20, index_mcp_flexion=90, index_pip=90, index_dip=60, middle_mcp_abduction=-5, middle_mcp_flexion=90, middle_pip=90, middle_dip=60, ring_mcp_abduction=5, ring_mcp_flexion=90, ring_pip=90, ring_dip=60, little_mcp_abduction=25, little_mcp_flexion=90, little_pip=90, little_dip=60, thumb_cmc_abduction=-15, thumb_cmc_flexion=45, thumb_mcp_abduction=-10, thumb_mcp_flexion=55, thumb_ip=60 | All five pass |
| flat_open | Neutral | All five pass |
| index_dip_0 | index_dip=0 | All five pass |
| index_dip_10 | index_dip=10 | All five pass |
| index_dip_20 | index_dip=20 | All five pass |
| index_dip_30 | index_dip=30 | All five pass |
| index_dip_40 | index_dip=40 | All five pass |
| index_dip_50 | index_dip=50 | All five pass |
| index_dip_60 | index_dip=60 | All five pass |
| index_dip_70 | index_dip=70 | All five pass |
| index_dip_80 | index_dip=80 | All five pass |
| index_mcp_abduction_-10 | index_mcp_abduction=-10 | All five pass |
| index_mcp_abduction_-20 | index_mcp_abduction=-20 | All five pass |
| index_mcp_abduction_0 | index_mcp_abduction=0 | All five pass |
| index_mcp_abduction_10 | index_mcp_abduction=10 | All five pass |
| index_mcp_abduction_20 | index_mcp_abduction=20 | All five pass |
| index_mcp_flexion_-15 | index_mcp_flexion=-15 | All five pass |
| index_mcp_flexion_-5 | index_mcp_flexion=-5 | All five pass |
| index_mcp_flexion_0 | index_mcp_flexion=0 | All five pass |
| index_mcp_flexion_15 | index_mcp_flexion=15 | All five pass |
| index_mcp_flexion_25 | index_mcp_flexion=25 | All five pass |
| index_mcp_flexion_35 | index_mcp_flexion=35 | All five pass |
| index_mcp_flexion_45 | index_mcp_flexion=45 | All five pass |
| index_mcp_flexion_5 | index_mcp_flexion=5 | All five pass |
| index_mcp_flexion_55 | index_mcp_flexion=55 | All five pass |
| index_mcp_flexion_65 | index_mcp_flexion=65 | All five pass |
| index_mcp_flexion_75 | index_mcp_flexion=75 | All five pass |
| index_mcp_flexion_85 | index_mcp_flexion=85 | All five pass |
| index_mcp_flexion_90 | index_mcp_flexion=90 | All five pass |
| index_pip_0 | index_pip=0 | All five pass |
| index_pip_10 | index_pip=10 | All five pass |
| index_pip_100 | index_pip=100 | All five pass |
| index_pip_110 | index_pip=110 | All five pass |
| index_pip_20 | index_pip=20 | All five pass |
| index_pip_30 | index_pip=30 | All five pass |
| index_pip_40 | index_pip=40 | All five pass |
| index_pip_50 | index_pip=50 | All five pass |
| index_pip_60 | index_pip=60 | All five pass |
| index_pip_70 | index_pip=70 | All five pass |
| index_pip_80 | index_pip=80 | All five pass |
| index_pip_90 | index_pip=90 | All five pass |
| little_dip_0 | little_dip=0 | All five pass |
| little_dip_10 | little_dip=10 | All five pass |
| little_dip_20 | little_dip=20 | All five pass |
| little_dip_30 | little_dip=30 | All five pass |
| little_dip_40 | little_dip=40 | All five pass |
| little_dip_50 | little_dip=50 | All five pass |
| little_dip_60 | little_dip=60 | All five pass |
| little_dip_70 | little_dip=70 | All five pass |
| little_dip_80 | little_dip=80 | All five pass |
| little_mcp_abduction_-15 | little_mcp_abduction=-15 | All five pass |
| little_mcp_abduction_-25 | little_mcp_abduction=-25 | All five pass |
| little_mcp_abduction_-5 | little_mcp_abduction=-5 | All five pass |
| little_mcp_abduction_0 | little_mcp_abduction=0 | All five pass |
| little_mcp_abduction_15 | little_mcp_abduction=15 | All five pass |
| little_mcp_abduction_25 | little_mcp_abduction=25 | All five pass |
| little_mcp_abduction_5 | little_mcp_abduction=5 | All five pass |
| little_mcp_flexion_-15 | little_mcp_flexion=-15 | All five pass |
| little_mcp_flexion_-5 | little_mcp_flexion=-5 | All five pass |
| little_mcp_flexion_0 | little_mcp_flexion=0 | All five pass |
| little_mcp_flexion_15 | little_mcp_flexion=15 | All five pass |
| little_mcp_flexion_25 | little_mcp_flexion=25 | All five pass |
| little_mcp_flexion_35 | little_mcp_flexion=35 | All five pass |
| little_mcp_flexion_45 | little_mcp_flexion=45 | All five pass |
| little_mcp_flexion_5 | little_mcp_flexion=5 | All five pass |
| little_mcp_flexion_55 | little_mcp_flexion=55 | All five pass |
| little_mcp_flexion_65 | little_mcp_flexion=65 | All five pass |
| little_mcp_flexion_75 | little_mcp_flexion=75 | All five pass |
| little_mcp_flexion_85 | little_mcp_flexion=85 | All five pass |
| little_mcp_flexion_90 | little_mcp_flexion=90 | All five pass |
| little_pip_0 | little_pip=0 | All five pass |
| little_pip_10 | little_pip=10 | All five pass |
| little_pip_100 | little_pip=100 | All five pass |
| little_pip_110 | little_pip=110 | All five pass |
| little_pip_20 | little_pip=20 | All five pass |
| little_pip_30 | little_pip=30 | All five pass |
| little_pip_40 | little_pip=40 | All five pass |
| little_pip_50 | little_pip=50 | All five pass |
| little_pip_60 | little_pip=60 | All five pass |
| little_pip_70 | little_pip=70 | All five pass |
| little_pip_80 | little_pip=80 | All five pass |
| little_pip_90 | little_pip=90 | All five pass |
| middle_dip_0 | middle_dip=0 | All five pass |
| middle_dip_10 | middle_dip=10 | All five pass |
| middle_dip_20 | middle_dip=20 | All five pass |
| middle_dip_30 | middle_dip=30 | All five pass |
| middle_dip_40 | middle_dip=40 | All five pass |
| middle_dip_50 | middle_dip=50 | All five pass |
| middle_dip_60 | middle_dip=60 | All five pass |
| middle_dip_70 | middle_dip=70 | All five pass |
| middle_dip_80 | middle_dip=80 | All five pass |
| middle_mcp_abduction_-15 | middle_mcp_abduction=-15 | All five pass |
| middle_mcp_abduction_-5 | middle_mcp_abduction=-5 | All five pass |
| middle_mcp_abduction_0 | middle_mcp_abduction=0 | All five pass |
| middle_mcp_abduction_15 | middle_mcp_abduction=15 | All five pass |
| middle_mcp_abduction_5 | middle_mcp_abduction=5 | All five pass |
| middle_mcp_flexion_-15 | middle_mcp_flexion=-15 | All five pass |
| middle_mcp_flexion_-5 | middle_mcp_flexion=-5 | All five pass |
| middle_mcp_flexion_0 | middle_mcp_flexion=0 | All five pass |
| middle_mcp_flexion_15 | middle_mcp_flexion=15 | All five pass |
| middle_mcp_flexion_25 | middle_mcp_flexion=25 | All five pass |
| middle_mcp_flexion_35 | middle_mcp_flexion=35 | All five pass |
| middle_mcp_flexion_45 | middle_mcp_flexion=45 | All five pass |
| middle_mcp_flexion_5 | middle_mcp_flexion=5 | All five pass |
| middle_mcp_flexion_55 | middle_mcp_flexion=55 | All five pass |
| middle_mcp_flexion_65 | middle_mcp_flexion=65 | All five pass |
| middle_mcp_flexion_75 | middle_mcp_flexion=75 | All five pass |
| middle_mcp_flexion_85 | middle_mcp_flexion=85 | All five pass |
| middle_mcp_flexion_90 | middle_mcp_flexion=90 | All five pass |
| middle_pip_0 | middle_pip=0 | All five pass |
| middle_pip_10 | middle_pip=10 | All five pass |
| middle_pip_100 | middle_pip=100 | All five pass |
| middle_pip_110 | middle_pip=110 | All five pass |
| middle_pip_20 | middle_pip=20 | All five pass |
| middle_pip_30 | middle_pip=30 | All five pass |
| middle_pip_40 | middle_pip=40 | All five pass |
| middle_pip_50 | middle_pip=50 | All five pass |
| middle_pip_60 | middle_pip=60 | All five pass |
| middle_pip_70 | middle_pip=70 | All five pass |
| middle_pip_80 | middle_pip=80 | All five pass |
| middle_pip_90 | middle_pip=90 | All five pass |
| palm_cup_0 | palm_cup=0 | All five pass |
| palm_cup_10 | palm_cup=10 | All five pass |
| palm_cup_20 | palm_cup=20 | All five pass |
| palm_cup_25 | palm_cup=25 | All five pass |
| precision_pinch_candidate | index_mcp_abduction=-17.409, index_mcp_flexion=74.6847, index_pip=57.9483, index_dip=21.9086, thumb_mcp_abduction=-11.4845, thumb_mcp_flexion=7.69786, thumb_ip=31.5647, thumb_cmc_abduction=-21.0468, thumb_cmc_flexion=37.4743 | All five pass |
| ring_dip_0 | ring_dip=0 | All five pass |
| ring_dip_10 | ring_dip=10 | All five pass |
| ring_dip_20 | ring_dip=20 | All five pass |
| ring_dip_30 | ring_dip=30 | All five pass |
| ring_dip_40 | ring_dip=40 | All five pass |
| ring_dip_50 | ring_dip=50 | All five pass |
| ring_dip_60 | ring_dip=60 | All five pass |
| ring_dip_70 | ring_dip=70 | All five pass |
| ring_dip_80 | ring_dip=80 | All five pass |
| ring_mcp_abduction_-15 | ring_mcp_abduction=-15 | All five pass |
| ring_mcp_abduction_-5 | ring_mcp_abduction=-5 | All five pass |
| ring_mcp_abduction_0 | ring_mcp_abduction=0 | All five pass |
| ring_mcp_abduction_15 | ring_mcp_abduction=15 | All five pass |
| ring_mcp_abduction_5 | ring_mcp_abduction=5 | All five pass |
| ring_mcp_flexion_-15 | ring_mcp_flexion=-15 | All five pass |
| ring_mcp_flexion_-5 | ring_mcp_flexion=-5 | All five pass |
| ring_mcp_flexion_0 | ring_mcp_flexion=0 | All five pass |
| ring_mcp_flexion_15 | ring_mcp_flexion=15 | All five pass |
| ring_mcp_flexion_25 | ring_mcp_flexion=25 | All five pass |
| ring_mcp_flexion_35 | ring_mcp_flexion=35 | All five pass |
| ring_mcp_flexion_45 | ring_mcp_flexion=45 | All five pass |
| ring_mcp_flexion_5 | ring_mcp_flexion=5 | All five pass |
| ring_mcp_flexion_55 | ring_mcp_flexion=55 | All five pass |
| ring_mcp_flexion_65 | ring_mcp_flexion=65 | All five pass |
| ring_mcp_flexion_75 | ring_mcp_flexion=75 | All five pass |
| ring_mcp_flexion_85 | ring_mcp_flexion=85 | All five pass |
| ring_mcp_flexion_90 | ring_mcp_flexion=90 | All five pass |
| ring_pip_0 | ring_pip=0 | All five pass |
| ring_pip_10 | ring_pip=10 | All five pass |
| ring_pip_100 | ring_pip=100 | All five pass |
| ring_pip_110 | ring_pip=110 | All five pass |
| ring_pip_20 | ring_pip=20 | All five pass |
| ring_pip_30 | ring_pip=30 | All five pass |
| ring_pip_40 | ring_pip=40 | All five pass |
| ring_pip_50 | ring_pip=50 | All five pass |
| ring_pip_60 | ring_pip=60 | All five pass |
| ring_pip_70 | ring_pip=70 | All five pass |
| ring_pip_80 | ring_pip=80 | All five pass |
| ring_pip_90 | ring_pip=90 | All five pass |
| thumb_cmc_abduction_-15 | thumb_cmc_abduction=-15 | All five pass |
| thumb_cmc_abduction_-25 | thumb_cmc_abduction=-25 | All five pass |
| thumb_cmc_abduction_-5 | thumb_cmc_abduction=-5 | All five pass |
| thumb_cmc_abduction_0 | thumb_cmc_abduction=0 | All five pass |
| thumb_cmc_abduction_15 | thumb_cmc_abduction=15 | All five pass |
| thumb_cmc_abduction_25 | thumb_cmc_abduction=25 | All five pass |
| thumb_cmc_abduction_35 | thumb_cmc_abduction=35 | All five pass |
| thumb_cmc_abduction_45 | thumb_cmc_abduction=45 | All five pass |
| thumb_cmc_abduction_5 | thumb_cmc_abduction=5 | All five pass |
| thumb_cmc_flexion_-15 | thumb_cmc_flexion=-15 | All five pass |
| thumb_cmc_flexion_-5 | thumb_cmc_flexion=-5 | All five pass |
| thumb_cmc_flexion_0 | thumb_cmc_flexion=0 | All five pass |
| thumb_cmc_flexion_15 | thumb_cmc_flexion=15 | All five pass |
| thumb_cmc_flexion_25 | thumb_cmc_flexion=25 | All five pass |
| thumb_cmc_flexion_35 | thumb_cmc_flexion=35 | All five pass |
| thumb_cmc_flexion_45 | thumb_cmc_flexion=45 | All five pass |
| thumb_cmc_flexion_5 | thumb_cmc_flexion=5 | All five pass |
| thumb_cmc_flexion_55 | thumb_cmc_flexion=55 | All five pass |
| thumb_cmc_flexion_65 | thumb_cmc_flexion=65 | All five pass |
| thumb_ip_0 | thumb_ip=0 | All five pass |
| thumb_ip_10 | thumb_ip=10 | All five pass |
| thumb_ip_20 | thumb_ip=20 | All five pass |
| thumb_ip_30 | thumb_ip=30 | All five pass |
| thumb_ip_40 | thumb_ip=40 | All five pass |
| thumb_ip_50 | thumb_ip=50 | All five pass |
| thumb_ip_60 | thumb_ip=60 | All five pass |
| thumb_ip_70 | thumb_ip=70 | All five pass |
| thumb_ip_80 | thumb_ip=80 | All five pass |
| thumb_ip_85 | thumb_ip=85 | All five pass |
| thumb_mcp_abduction_-15 | thumb_mcp_abduction=-15 | All five pass |
| thumb_mcp_abduction_-5 | thumb_mcp_abduction=-5 | All five pass |
| thumb_mcp_abduction_0 | thumb_mcp_abduction=0 | All five pass |
| thumb_mcp_abduction_15 | thumb_mcp_abduction=15 | All five pass |
| thumb_mcp_abduction_5 | thumb_mcp_abduction=5 | All five pass |
| thumb_mcp_flexion_0 | thumb_mcp_flexion=0 | All five pass |
| thumb_mcp_flexion_10 | thumb_mcp_flexion=10 | All five pass |
| thumb_mcp_flexion_20 | thumb_mcp_flexion=20 | All five pass |
| thumb_mcp_flexion_30 | thumb_mcp_flexion=30 | All five pass |
| thumb_mcp_flexion_40 | thumb_mcp_flexion=40 | All five pass |
| thumb_mcp_flexion_50 | thumb_mcp_flexion=50 | All five pass |
| thumb_mcp_flexion_60 | thumb_mcp_flexion=60 | All five pass |
| thumb_mcp_flexion_70 | thumb_mcp_flexion=70 | All five pass |
| wrist_abduction_-10 | wrist_abduction=-10 | All five pass |
| wrist_abduction_-20 | wrist_abduction=-20 | All five pass |
| wrist_abduction_0 | wrist_abduction=0 | All five pass |
| wrist_abduction_10 | wrist_abduction=10 | All five pass |
| wrist_abduction_20 | wrist_abduction=20 | All five pass |
| wrist_flexion_-15 | wrist_flexion=-15 | All five pass |
| wrist_flexion_-25 | wrist_flexion=-25 | All five pass |
| wrist_flexion_-35 | wrist_flexion=-35 | All five pass |
| wrist_flexion_-45 | wrist_flexion=-45 | All five pass |
| wrist_flexion_-5 | wrist_flexion=-5 | All five pass |
| wrist_flexion_0 | wrist_flexion=0 | All five pass |
| wrist_flexion_15 | wrist_flexion=15 | All five pass |
| wrist_flexion_25 | wrist_flexion=25 | All five pass |
| wrist_flexion_35 | wrist_flexion=35 | All five pass |
| wrist_flexion_45 | wrist_flexion=45 | All five pass |
| wrist_flexion_5 | wrist_flexion=5 | All five pass |
| wrist_flexion_55 | wrist_flexion=55 | All five pass |
| wrist_flexion_60 | wrist_flexion=60 | All five pass |

Exact inputs, every matrix entry and scalar extrema are retained in [native_r13_routing_tables.json](native_r13_routing_tables.json).
