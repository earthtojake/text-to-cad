"""A real continuous STEP swept tube for flexible-animation integration checks."""
from cadgen import build123d as bd
from cadgen import step


ANIMATION_JS = r'''const rest = {normal:[0,0,1],segments:[{kind:'line',start:[0,0,8],end:[60,0,8]}]};
export const clips = {
  bend: {
    label:'Continuous swept tube — length 60 mm', duration:1, loop:false,
    update(t,m) {
      const angle=t*Math.PI/2;
      const path=angle<1e-8?rest:{normal:[0,0,1],segments:[{
        kind:'arc',center:[0,60/angle,8],axis:[0,0,1],start:[0,0,8],sweepDeg:angle*180/Math.PI
      }]};
      m.get('continuous_swept_tube').deformTube({rest,path,maxSegmentLength:.5,braid:{pitch:5,depth:.06,strands:8},twistDeg:180*t});
    }
  }
};
'''


@step(out="../STEP/runtime_fixture.step", animation=ANIMATION_JS)
def runtime_fixture():
    centerline = bd.Edge.make_line((0, 0, 8), (60, 0, 8))
    profile = bd.Plane(origin=(0, 0, 8), z_dir=(1, 0, 0)) * bd.Circle(0.8)
    tube = bd.sweep(profile, path=centerline)
    tube.label = "continuous_swept_tube"
    tube.color = bd.Color(0.86, 0.32, 0.11)
    start = bd.Pos(0, 0, 8) * bd.Sphere(1.2)
    start.label = "fixed_start_marker"
    start.color = bd.Color(0.18, 0.2, 0.23)
    return bd.Compound(children=[tube, start])


if __name__ == "__main__":
    runtime_fixture()
