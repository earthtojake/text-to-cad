const rest = {normal:[0,0,1],segments:[{kind:'line',start:[0,0,8],end:[60,0,8]}]};
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
