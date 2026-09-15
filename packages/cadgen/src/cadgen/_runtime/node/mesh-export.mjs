#!/usr/bin/env node
var Ma=Object.defineProperty;var p=(i,t)=>Ma(i,"name",{value:t,configurable:!0});import nn from"node:fs";import sn from"node:path";function sr(i){let t=new DataView(i,0,12);if(t.getUint32(0,!0)!==1179800915)throw new Error("not a SURF container");let e=t.getUint32(4,!0);if(e!==2)throw new Error(`unsupported SURF version ${e}`);let n=t.getUint32(8,!0),s=new Uint8Array(i,12,n),r=JSON.parse(new TextDecoder().decode(s)),o=12+n,a=new Float32Array(i.slice(o,o+(i.byteLength-o>>2<<2)));return{index:r,floats:a}}p(sr,"parseSurf");function se(i,t){let[e,n]=t;return i.subarray(e,e+n)}p(se,"floatSpan");var vr=1;var Mr=3;var Oi=0,Bi=1,zi=2,ki=3,Vi=4,Gi=5,Hi=6,Wi=7,br=0,Sr=1,Ar=2;var cs=1,ls=2,us=3,hs=4,fs=5,ds=6,ps=7;var ms=300,wr=301,gs=302;var Tr=306,Xi=1e3,hn=1001,qi=1002;var Er=1006;var Cr=1008;var Rr=1009;var Ir=1015;var Pr=1023;var pn=2300,Wn=2301,Gn=2302,$i=2303,Yi=2400,Zi=2401,Ji=2402;var xs="",kt="srgb",Ki="srgb-linear",ji="linear",Hn="srgb";var Qi=35044;var fn=2e3,ts=2001;function ba(i){for(let t=i.length-1;t>=0;--t)if(i[t]>=65535)return!0;return!1}p(ba,"arrayNeedsUint32");function Sa(i){return ArrayBuffer.isView(i)&&!(i instanceof DataView)}p(Sa,"isTypedArray");function es(i){return document.createElementNS("http://www.w3.org/1999/xhtml",i)}p(es,"createElementNS");var rr={},Xn=null;function Lr(i){let t=i[0];if(typeof t=="string"&&t.startsWith("TSL:")){let e=i[1];e&&e.isStackTrace?i[0]+=" "+e.getLocation():i[1]='Stack trace not available. Enable "THREE.Node.captureStackTrace" to capture stack traces.'}return i}p(Lr,"enhanceLogMessage");function pt(...i){i=Lr(i);let t="THREE."+i.shift();if(Xn)Xn("warn",t,...i);else{let e=i[0];e&&e.isStackTrace?console.warn(e.getError(t)):console.warn(t,...i)}}p(pt,"warn");function ot(...i){i=Lr(i);let t="THREE."+i.shift();if(Xn)Xn("error",t,...i);else{let e=i[0];e&&e.isStackTrace?console.error(e.getError(t)):console.error(t,...i)}}p(ot,"error");function Ve(...i){let t=i.join(" ");t in rr||(rr[t]=!0,pt(...i))}p(Ve,"warnOnce");var Aa={[Oi]:Bi,[zi]:Hi,[Vi]:Wi,[ki]:Gi,[Bi]:Oi,[Hi]:zi,[Wi]:Vi,[Gi]:ki},ve=class{static{p(this,"EventDispatcher")}addEventListener(t,e){this._listeners===void 0&&(this._listeners={});let n=this._listeners;n[t]===void 0&&(n[t]=[]),n[t].indexOf(e)===-1&&n[t].push(e)}hasEventListener(t,e){let n=this._listeners;return n===void 0?!1:n[t]!==void 0&&n[t].indexOf(e)!==-1}removeEventListener(t,e){let n=this._listeners;if(n===void 0)return;let s=n[t];if(s!==void 0){let r=s.indexOf(e);r!==-1&&s.splice(r,1)}}dispatchEvent(t){let e=this._listeners;if(e===void 0)return;let n=e[t.type];if(n!==void 0){t.target=this;let s=n.slice(0);for(let r=0,o=s.length;r<o;r++)s[r].call(this,t);t.target=null}}},vt=["00","01","02","03","04","05","06","07","08","09","0a","0b","0c","0d","0e","0f","10","11","12","13","14","15","16","17","18","19","1a","1b","1c","1d","1e","1f","20","21","22","23","24","25","26","27","28","29","2a","2b","2c","2d","2e","2f","30","31","32","33","34","35","36","37","38","39","3a","3b","3c","3d","3e","3f","40","41","42","43","44","45","46","47","48","49","4a","4b","4c","4d","4e","4f","50","51","52","53","54","55","56","57","58","59","5a","5b","5c","5d","5e","5f","60","61","62","63","64","65","66","67","68","69","6a","6b","6c","6d","6e","6f","70","71","72","73","74","75","76","77","78","79","7a","7b","7c","7d","7e","7f","80","81","82","83","84","85","86","87","88","89","8a","8b","8c","8d","8e","8f","90","91","92","93","94","95","96","97","98","99","9a","9b","9c","9d","9e","9f","a0","a1","a2","a3","a4","a5","a6","a7","a8","a9","aa","ab","ac","ad","ae","af","b0","b1","b2","b3","b4","b5","b6","b7","b8","b9","ba","bb","bc","bd","be","bf","c0","c1","c2","c3","c4","c5","c6","c7","c8","c9","ca","cb","cc","cd","ce","cf","d0","d1","d2","d3","d4","d5","d6","d7","d8","d9","da","db","dc","dd","de","df","e0","e1","e2","e3","e4","e5","e6","e7","e8","e9","ea","eb","ec","ed","ee","ef","f0","f1","f2","f3","f4","f5","f6","f7","f8","f9","fa","fb","fc","fd","fe","ff"];var Qf=Math.PI/180,wa=180/Math.PI;function ci(){let i=Math.random()*4294967295|0,t=Math.random()*4294967295|0,e=Math.random()*4294967295|0,n=Math.random()*4294967295|0;return(vt[i&255]+vt[i>>8&255]+vt[i>>16&255]+vt[i>>24&255]+"-"+vt[t&255]+vt[t>>8&255]+"-"+vt[t>>16&15|64]+vt[t>>24&255]+"-"+vt[e&63|128]+vt[e>>8&255]+"-"+vt[e>>16&255]+vt[e>>24&255]+vt[n&255]+vt[n>>8&255]+vt[n>>16&255]+vt[n>>24&255]).toLowerCase()}p(ci,"generateUUID");function j(i,t,e){return Math.max(t,Math.min(e,i))}p(j,"clamp");function Ta(i,t){return(i%t+t)%t}p(Ta,"euclideanModulo");function Ei(i,t,e){return(1-e)*i+e*t}p(Ei,"lerp");function on(i,t){switch(t.constructor){case Float32Array:return i;case Uint32Array:return i/4294967295;case Uint16Array:return i/65535;case Uint8Array:return i/255;case Int32Array:return Math.max(i/2147483647,-1);case Int16Array:return Math.max(i/32767,-1);case Int8Array:return Math.max(i/127,-1);default:throw new Error("THREE.MathUtils: Invalid component type.")}}p(on,"denormalize");function wt(i,t){switch(t.constructor){case Float32Array:return i;case Uint32Array:return Math.round(i*4294967295);case Uint16Array:return Math.round(i*65535);case Uint8Array:return Math.round(i*255);case Int32Array:return Math.round(i*2147483647);case Int16Array:return Math.round(i*32767);case Int8Array:return Math.round(i*127);default:throw new Error("THREE.MathUtils: Invalid component type.")}}p(wt,"normalize");var mt=class i{static{p(this,"Vector2")}static{i.prototype.isVector2=!0}constructor(t=0,e=0){this.x=t,this.y=e}get width(){return this.x}set width(t){this.x=t}get height(){return this.y}set height(t){this.y=t}set(t,e){return this.x=t,this.y=e,this}setScalar(t){return this.x=t,this.y=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;default:throw new Error("THREE.Vector2: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;default:throw new Error("THREE.Vector2: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y)}copy(t){return this.x=t.x,this.y=t.y,this}add(t){return this.x+=t.x,this.y+=t.y,this}addScalar(t){return this.x+=t,this.y+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this}subScalar(t){return this.x-=t,this.y-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this}multiply(t){return this.x*=t.x,this.y*=t.y,this}multiplyScalar(t){return this.x*=t,this.y*=t,this}divide(t){return this.x/=t.x,this.y/=t.y,this}divideScalar(t){return this.multiplyScalar(1/t)}applyMatrix3(t){let e=this.x,n=this.y,s=t.elements;return this.x=s[0]*e+s[3]*n+s[6],this.y=s[1]*e+s[4]*n+s[7],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this}clamp(t,e){return this.x=j(this.x,t.x,e.x),this.y=j(this.y,t.y,e.y),this}clampScalar(t,e){return this.x=j(this.x,t,e),this.y=j(this.y,t,e),this}clampLength(t,e){let n=this.length();return this.divideScalar(n||1).multiplyScalar(j(n,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this}negate(){return this.x=-this.x,this.y=-this.y,this}dot(t){return this.x*t.x+this.y*t.y}cross(t){return this.x*t.y-this.y*t.x}lengthSq(){return this.x*this.x+this.y*this.y}length(){return Math.sqrt(this.x*this.x+this.y*this.y)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)}normalize(){return this.divideScalar(this.length()||1)}angle(){return Math.atan2(-this.y,-this.x)+Math.PI}angleTo(t){let e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;let n=this.dot(t)/e;return Math.acos(j(n,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){let e=this.x-t.x,n=this.y-t.y;return e*e+n*n}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this}lerpVectors(t,e,n){return this.x=t.x+(e.x-t.x)*n,this.y=t.y+(e.y-t.y)*n,this}equals(t){return t.x===this.x&&t.y===this.y}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this}rotateAround(t,e){let n=Math.cos(e),s=Math.sin(e),r=this.x-t.x,o=this.y-t.y;return this.x=r*n-o*s+t.x,this.y=r*s+o*n+t.y,this}random(){return this.x=Math.random(),this.y=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y}},$t=class{static{p(this,"Quaternion")}constructor(t=0,e=0,n=0,s=1){this.isQuaternion=!0,this._x=t,this._y=e,this._z=n,this._w=s}static slerpFlat(t,e,n,s,r,o,a){let c=n[s+0],l=n[s+1],u=n[s+2],h=n[s+3],f=r[o+0],d=r[o+1],m=r[o+2],g=r[o+3];if(h!==g||c!==f||l!==d||u!==m){let _=c*f+l*d+u*m+h*g;_<0&&(f=-f,d=-d,m=-m,g=-g,_=-_);let x=1-a;if(_<.9995){let y=Math.acos(_),v=Math.sin(y);x=Math.sin(x*y)/v,a=Math.sin(a*y)/v,c=c*x+f*a,l=l*x+d*a,u=u*x+m*a,h=h*x+g*a}else{c=c*x+f*a,l=l*x+d*a,u=u*x+m*a,h=h*x+g*a;let y=1/Math.sqrt(c*c+l*l+u*u+h*h);c*=y,l*=y,u*=y,h*=y}}t[e]=c,t[e+1]=l,t[e+2]=u,t[e+3]=h}static multiplyQuaternionsFlat(t,e,n,s,r,o){let a=n[s],c=n[s+1],l=n[s+2],u=n[s+3],h=r[o],f=r[o+1],d=r[o+2],m=r[o+3];return t[e]=a*m+u*h+c*d-l*f,t[e+1]=c*m+u*f+l*h-a*d,t[e+2]=l*m+u*d+a*f-c*h,t[e+3]=u*m-a*h-c*f-l*d,t}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get w(){return this._w}set w(t){this._w=t,this._onChangeCallback()}set(t,e,n,s){return this._x=t,this._y=e,this._z=n,this._w=s,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._w)}copy(t){return this._x=t.x,this._y=t.y,this._z=t.z,this._w=t.w,this._onChangeCallback(),this}setFromEuler(t,e=!0){let n=t._x,s=t._y,r=t._z,o=t._order,a=Math.cos,c=Math.sin,l=a(n/2),u=a(s/2),h=a(r/2),f=c(n/2),d=c(s/2),m=c(r/2);switch(o){case"XYZ":this._x=f*u*h+l*d*m,this._y=l*d*h-f*u*m,this._z=l*u*m+f*d*h,this._w=l*u*h-f*d*m;break;case"YXZ":this._x=f*u*h+l*d*m,this._y=l*d*h-f*u*m,this._z=l*u*m-f*d*h,this._w=l*u*h+f*d*m;break;case"ZXY":this._x=f*u*h-l*d*m,this._y=l*d*h+f*u*m,this._z=l*u*m+f*d*h,this._w=l*u*h-f*d*m;break;case"ZYX":this._x=f*u*h-l*d*m,this._y=l*d*h+f*u*m,this._z=l*u*m-f*d*h,this._w=l*u*h+f*d*m;break;case"YZX":this._x=f*u*h+l*d*m,this._y=l*d*h+f*u*m,this._z=l*u*m-f*d*h,this._w=l*u*h-f*d*m;break;case"XZY":this._x=f*u*h-l*d*m,this._y=l*d*h-f*u*m,this._z=l*u*m+f*d*h,this._w=l*u*h+f*d*m;break;default:pt("Quaternion: .setFromEuler() encountered an unknown order: "+o)}return e===!0&&this._onChangeCallback(),this}setFromAxisAngle(t,e){let n=e/2,s=Math.sin(n);return this._x=t.x*s,this._y=t.y*s,this._z=t.z*s,this._w=Math.cos(n),this._onChangeCallback(),this}setFromRotationMatrix(t){let e=t.elements,n=e[0],s=e[4],r=e[8],o=e[1],a=e[5],c=e[9],l=e[2],u=e[6],h=e[10],f=n+a+h;if(f>0){let d=.5/Math.sqrt(f+1);this._w=.25/d,this._x=(u-c)*d,this._y=(r-l)*d,this._z=(o-s)*d}else if(n>a&&n>h){let d=2*Math.sqrt(1+n-a-h);this._w=(u-c)/d,this._x=.25*d,this._y=(s+o)/d,this._z=(r+l)/d}else if(a>h){let d=2*Math.sqrt(1+a-n-h);this._w=(r-l)/d,this._x=(s+o)/d,this._y=.25*d,this._z=(c+u)/d}else{let d=2*Math.sqrt(1+h-n-a);this._w=(o-s)/d,this._x=(r+l)/d,this._y=(c+u)/d,this._z=.25*d}return this._onChangeCallback(),this}setFromUnitVectors(t,e){let n=t.dot(e)+1;return n<1e-8?(n=0,Math.abs(t.x)>Math.abs(t.z)?(this._x=-t.y,this._y=t.x,this._z=0,this._w=n):(this._x=0,this._y=-t.z,this._z=t.y,this._w=n)):(this._x=t.y*e.z-t.z*e.y,this._y=t.z*e.x-t.x*e.z,this._z=t.x*e.y-t.y*e.x,this._w=n),this.normalize()}angleTo(t){return 2*Math.acos(Math.abs(j(this.dot(t),-1,1)))}rotateTowards(t,e){let n=this.angleTo(t);if(n===0)return this;let s=Math.min(1,e/n);return this.slerp(t,s),this}identity(){return this.set(0,0,0,1)}invert(){return this.conjugate()}conjugate(){return this._x*=-1,this._y*=-1,this._z*=-1,this._onChangeCallback(),this}dot(t){return this._x*t._x+this._y*t._y+this._z*t._z+this._w*t._w}lengthSq(){return this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w}length(){return Math.sqrt(this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w)}normalize(){let t=this.length();return t===0?(this._x=0,this._y=0,this._z=0,this._w=1):(t=1/t,this._x=this._x*t,this._y=this._y*t,this._z=this._z*t,this._w=this._w*t),this._onChangeCallback(),this}multiply(t){return this.multiplyQuaternions(this,t)}premultiply(t){return this.multiplyQuaternions(t,this)}multiplyQuaternions(t,e){let n=t._x,s=t._y,r=t._z,o=t._w,a=e._x,c=e._y,l=e._z,u=e._w;return this._x=n*u+o*a+s*l-r*c,this._y=s*u+o*c+r*a-n*l,this._z=r*u+o*l+n*c-s*a,this._w=o*u-n*a-s*c-r*l,this._onChangeCallback(),this}slerp(t,e){let n=t._x,s=t._y,r=t._z,o=t._w,a=this.dot(t);a<0&&(n=-n,s=-s,r=-r,o=-o,a=-a);let c=1-e;if(a<.9995){let l=Math.acos(a),u=Math.sin(l);c=Math.sin(c*l)/u,e=Math.sin(e*l)/u,this._x=this._x*c+n*e,this._y=this._y*c+s*e,this._z=this._z*c+r*e,this._w=this._w*c+o*e,this._onChangeCallback()}else this._x=this._x*c+n*e,this._y=this._y*c+s*e,this._z=this._z*c+r*e,this._w=this._w*c+o*e,this.normalize();return this}slerpQuaternions(t,e,n){return this.copy(t).slerp(e,n)}random(){let t=2*Math.PI*Math.random(),e=2*Math.PI*Math.random(),n=Math.random(),s=Math.sqrt(1-n),r=Math.sqrt(n);return this.set(s*Math.sin(t),s*Math.cos(t),r*Math.sin(e),r*Math.cos(e))}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._w===this._w}fromArray(t,e=0){return this._x=t[e],this._y=t[e+1],this._z=t[e+2],this._w=t[e+3],this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._w,t}fromBufferAttribute(t,e){return this._x=t.getX(e),this._y=t.getY(e),this._z=t.getZ(e),this._w=t.getW(e),this._onChangeCallback(),this}toJSON(){return this.toArray()}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._w}},V=class i{static{p(this,"Vector3")}static{i.prototype.isVector3=!0}constructor(t=0,e=0,n=0){this.x=t,this.y=e,this.z=n}set(t,e,n){return n===void 0&&(n=this.z),this.x=t,this.y=e,this.z=n,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;default:throw new Error("THREE.Vector3: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;default:throw new Error("THREE.Vector3: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this}multiplyVectors(t,e){return this.x=t.x*e.x,this.y=t.y*e.y,this.z=t.z*e.z,this}applyEuler(t){return this.applyQuaternion(or.setFromEuler(t))}applyAxisAngle(t,e){return this.applyQuaternion(or.setFromAxisAngle(t,e))}applyMatrix3(t){let e=this.x,n=this.y,s=this.z,r=t.elements;return this.x=r[0]*e+r[3]*n+r[6]*s,this.y=r[1]*e+r[4]*n+r[7]*s,this.z=r[2]*e+r[5]*n+r[8]*s,this}applyNormalMatrix(t){return this.applyMatrix3(t).normalize()}applyMatrix4(t){let e=this.x,n=this.y,s=this.z,r=t.elements,o=1/(r[3]*e+r[7]*n+r[11]*s+r[15]);return this.x=(r[0]*e+r[4]*n+r[8]*s+r[12])*o,this.y=(r[1]*e+r[5]*n+r[9]*s+r[13])*o,this.z=(r[2]*e+r[6]*n+r[10]*s+r[14])*o,this}applyQuaternion(t){let e=this.x,n=this.y,s=this.z,r=t.x,o=t.y,a=t.z,c=t.w,l=2*(o*s-a*n),u=2*(a*e-r*s),h=2*(r*n-o*e);return this.x=e+c*l+o*h-a*u,this.y=n+c*u+a*l-r*h,this.z=s+c*h+r*u-o*l,this}project(t){return this.applyMatrix4(t.matrixWorldInverse).applyMatrix4(t.projectionMatrix)}unproject(t){return this.applyMatrix4(t.projectionMatrixInverse).applyMatrix4(t.matrixWorld)}transformDirection(t){let e=this.x,n=this.y,s=this.z,r=t.elements;return this.x=r[0]*e+r[4]*n+r[8]*s,this.y=r[1]*e+r[5]*n+r[9]*s,this.z=r[2]*e+r[6]*n+r[10]*s,this.normalize()}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this}divideScalar(t){return this.multiplyScalar(1/t)}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this}clamp(t,e){return this.x=j(this.x,t.x,e.x),this.y=j(this.y,t.y,e.y),this.z=j(this.z,t.z,e.z),this}clampScalar(t,e){return this.x=j(this.x,t,e),this.y=j(this.y,t,e),this.z=j(this.z,t,e),this}clampLength(t,e){let n=this.length();return this.divideScalar(n||1).multiplyScalar(j(n,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this}lerpVectors(t,e,n){return this.x=t.x+(e.x-t.x)*n,this.y=t.y+(e.y-t.y)*n,this.z=t.z+(e.z-t.z)*n,this}cross(t){return this.crossVectors(this,t)}crossVectors(t,e){let n=t.x,s=t.y,r=t.z,o=e.x,a=e.y,c=e.z;return this.x=s*c-r*a,this.y=r*o-n*c,this.z=n*a-s*o,this}projectOnVector(t){let e=t.lengthSq();if(e===0)return this.set(0,0,0);let n=t.dot(this)/e;return this.copy(t).multiplyScalar(n)}projectOnPlane(t){return Ci.copy(this).projectOnVector(t),this.sub(Ci)}reflect(t){return this.sub(Ci.copy(t).multiplyScalar(2*this.dot(t)))}angleTo(t){let e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;let n=this.dot(t)/e;return Math.acos(j(n,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){let e=this.x-t.x,n=this.y-t.y,s=this.z-t.z;return e*e+n*n+s*s}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)+Math.abs(this.z-t.z)}setFromSpherical(t){return this.setFromSphericalCoords(t.radius,t.phi,t.theta)}setFromSphericalCoords(t,e,n){let s=Math.sin(e)*t;return this.x=s*Math.sin(n),this.y=Math.cos(e)*t,this.z=s*Math.cos(n),this}setFromCylindrical(t){return this.setFromCylindricalCoords(t.radius,t.theta,t.y)}setFromCylindricalCoords(t,e,n){return this.x=t*Math.sin(e),this.y=n,this.z=t*Math.cos(e),this}setFromMatrixPosition(t){let e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this}setFromMatrixScale(t){let e=this.setFromMatrixColumn(t,0).length(),n=this.setFromMatrixColumn(t,1).length(),s=this.setFromMatrixColumn(t,2).length();return this.x=e,this.y=n,this.z=s,this}setFromMatrixColumn(t,e){return this.fromArray(t.elements,e*4)}setFromMatrix3Column(t,e){return this.fromArray(t.elements,e*3)}setFromEuler(t){return this.x=t._x,this.y=t._y,this.z=t._z,this}setFromColor(t){return this.x=t.r,this.y=t.g,this.z=t.b,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this}randomDirection(){let t=Math.random()*Math.PI*2,e=Math.random()*2-1,n=Math.sqrt(1-e*e);return this.x=n*Math.cos(t),this.y=e,this.z=n*Math.sin(t),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z}},Ci=new V,or=new $t,Y=class i{static{p(this,"Matrix3")}static{i.prototype.isMatrix3=!0}constructor(t,e,n,s,r,o,a,c,l){this.elements=[1,0,0,0,1,0,0,0,1],t!==void 0&&this.set(t,e,n,s,r,o,a,c,l)}set(t,e,n,s,r,o,a,c,l){let u=this.elements;return u[0]=t,u[1]=s,u[2]=a,u[3]=e,u[4]=r,u[5]=c,u[6]=n,u[7]=o,u[8]=l,this}identity(){return this.set(1,0,0,0,1,0,0,0,1),this}copy(t){let e=this.elements,n=t.elements;return e[0]=n[0],e[1]=n[1],e[2]=n[2],e[3]=n[3],e[4]=n[4],e[5]=n[5],e[6]=n[6],e[7]=n[7],e[8]=n[8],this}extractBasis(t,e,n){return t.setFromMatrix3Column(this,0),e.setFromMatrix3Column(this,1),n.setFromMatrix3Column(this,2),this}setFromMatrix4(t){let e=t.elements;return this.set(e[0],e[4],e[8],e[1],e[5],e[9],e[2],e[6],e[10]),this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){let n=t.elements,s=e.elements,r=this.elements,o=n[0],a=n[3],c=n[6],l=n[1],u=n[4],h=n[7],f=n[2],d=n[5],m=n[8],g=s[0],_=s[3],x=s[6],y=s[1],v=s[4],b=s[7],S=s[2],A=s[5],M=s[8];return r[0]=o*g+a*y+c*S,r[3]=o*_+a*v+c*A,r[6]=o*x+a*b+c*M,r[1]=l*g+u*y+h*S,r[4]=l*_+u*v+h*A,r[7]=l*x+u*b+h*M,r[2]=f*g+d*y+m*S,r[5]=f*_+d*v+m*A,r[8]=f*x+d*b+m*M,this}multiplyScalar(t){let e=this.elements;return e[0]*=t,e[3]*=t,e[6]*=t,e[1]*=t,e[4]*=t,e[7]*=t,e[2]*=t,e[5]*=t,e[8]*=t,this}determinant(){let t=this.elements,e=t[0],n=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8];return e*o*u-e*a*l-n*r*u+n*a*c+s*r*l-s*o*c}invert(){let t=this.elements,e=t[0],n=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8],h=u*o-a*l,f=a*c-u*r,d=l*r-o*c,m=e*h+n*f+s*d;if(m===0)return this.set(0,0,0,0,0,0,0,0,0);let g=1/m;return t[0]=h*g,t[1]=(s*l-u*n)*g,t[2]=(a*n-s*o)*g,t[3]=f*g,t[4]=(u*e-s*c)*g,t[5]=(s*r-a*e)*g,t[6]=d*g,t[7]=(n*c-l*e)*g,t[8]=(o*e-n*r)*g,this}transpose(){let t,e=this.elements;return t=e[1],e[1]=e[3],e[3]=t,t=e[2],e[2]=e[6],e[6]=t,t=e[5],e[5]=e[7],e[7]=t,this}getNormalMatrix(t){return this.setFromMatrix4(t).invert().transpose()}transposeIntoArray(t){let e=this.elements;return t[0]=e[0],t[1]=e[3],t[2]=e[6],t[3]=e[1],t[4]=e[4],t[5]=e[7],t[6]=e[2],t[7]=e[5],t[8]=e[8],this}setUvTransform(t,e,n,s,r,o,a){let c=Math.cos(r),l=Math.sin(r);return this.set(n*c,n*l,-n*(c*o+l*a)+o+t,-s*l,s*c,-s*(-l*o+c*a)+a+e,0,0,1),this}scale(t,e){return Ve("Matrix3: .scale() is deprecated. Use .makeScale() instead."),this.premultiply(Ri.makeScale(t,e)),this}rotate(t){return Ve("Matrix3: .rotate() is deprecated. Use .makeRotation() instead."),this.premultiply(Ri.makeRotation(-t)),this}translate(t,e){return Ve("Matrix3: .translate() is deprecated. Use .makeTranslation() instead."),this.premultiply(Ri.makeTranslation(t,e)),this}makeTranslation(t,e){return t.isVector2?this.set(1,0,t.x,0,1,t.y,0,0,1):this.set(1,0,t,0,1,e,0,0,1),this}makeRotation(t){let e=Math.cos(t),n=Math.sin(t);return this.set(e,-n,0,n,e,0,0,0,1),this}makeScale(t,e){return this.set(t,0,0,0,e,0,0,0,1),this}equals(t){let e=this.elements,n=t.elements;for(let s=0;s<9;s++)if(e[s]!==n[s])return!1;return!0}fromArray(t,e=0){for(let n=0;n<9;n++)this.elements[n]=t[n+e];return this}toArray(t=[],e=0){let n=this.elements;return t[e]=n[0],t[e+1]=n[1],t[e+2]=n[2],t[e+3]=n[3],t[e+4]=n[4],t[e+5]=n[5],t[e+6]=n[6],t[e+7]=n[7],t[e+8]=n[8],t}clone(){return new this.constructor().fromArray(this.elements)}},Ri=new Y,ar=new Y().set(.4123908,.3575843,.1804808,.212639,.7151687,.0721923,.0193308,.1191948,.9505322),cr=new Y().set(3.2409699,-1.5373832,-.4986108,-.9692436,1.8759675,.0415551,.0556301,-.203977,1.0569715);function Ea(){let i={enabled:!0,workingColorSpace:Ki,spaces:{},convert:p(function(s,r,o){return this.enabled===!1||r===o||!r||!o||(this.spaces[r].transfer===Hn&&(s.r=Qt(s.r),s.g=Qt(s.g),s.b=Qt(s.b)),this.spaces[r].primaries!==this.spaces[o].primaries&&(s.applyMatrix3(this.spaces[r].toXYZ),s.applyMatrix3(this.spaces[o].fromXYZ)),this.spaces[o].transfer===Hn&&(s.r=Ge(s.r),s.g=Ge(s.g),s.b=Ge(s.b))),s},"convert"),workingToColorSpace:p(function(s,r){return this.convert(s,this.workingColorSpace,r)},"workingToColorSpace"),colorSpaceToWorking:p(function(s,r){return this.convert(s,r,this.workingColorSpace)},"colorSpaceToWorking"),getPrimaries:p(function(s){return this.spaces[s].primaries},"getPrimaries"),getTransfer:p(function(s){return s===xs?ji:this.spaces[s].transfer},"getTransfer"),getToneMappingMode:p(function(s){return this.spaces[s].outputColorSpaceConfig.toneMappingMode||"standard"},"getToneMappingMode"),getLuminanceCoefficients:p(function(s,r=this.workingColorSpace){return s.fromArray(this.spaces[r].luminanceCoefficients)},"getLuminanceCoefficients"),define:p(function(s){Object.assign(this.spaces,s)},"define"),_getMatrix:p(function(s,r,o){return s.copy(this.spaces[r].toXYZ).multiply(this.spaces[o].fromXYZ)},"_getMatrix"),_getDrawingBufferColorSpace:p(function(s){return this.spaces[s].outputColorSpaceConfig.drawingBufferColorSpace},"_getDrawingBufferColorSpace"),_getUnpackColorSpace:p(function(s=this.workingColorSpace){return this.spaces[s].workingColorSpaceConfig.unpackColorSpace},"_getUnpackColorSpace"),fromWorkingColorSpace:p(function(s,r){return Ve("ColorManagement: .fromWorkingColorSpace() has been renamed to .workingToColorSpace()."),i.workingToColorSpace(s,r)},"fromWorkingColorSpace"),toWorkingColorSpace:p(function(s,r){return Ve("ColorManagement: .toWorkingColorSpace() has been renamed to .colorSpaceToWorking()."),i.colorSpaceToWorking(s,r)},"toWorkingColorSpace")},t=[.64,.33,.3,.6,.15,.06],e=[.2126,.7152,.0722],n=[.3127,.329];return i.define({[Ki]:{primaries:t,whitePoint:n,transfer:ji,toXYZ:ar,fromXYZ:cr,luminanceCoefficients:e,workingColorSpaceConfig:{unpackColorSpace:kt},outputColorSpaceConfig:{drawingBufferColorSpace:kt}},[kt]:{primaries:t,whitePoint:n,transfer:Hn,toXYZ:ar,fromXYZ:cr,luminanceCoefficients:e,outputColorSpaceConfig:{drawingBufferColorSpace:kt}}}),i}p(Ea,"createColorManagement");var zt=Ea();function Qt(i){return i<.04045?i*.0773993808:Math.pow(i*.9478672986+.0521327014,2.4)}p(Qt,"SRGBToLinear");function Ge(i){return i<.0031308?i*12.92:1.055*Math.pow(i,.41666)-.055}p(Ge,"LinearToSRGB");var Ne,qn=class{static{p(this,"ImageUtils")}static getDataURL(t,e="image/png"){if(/^data:/i.test(t.src)||typeof HTMLCanvasElement>"u")return t.src;let n;if(t instanceof HTMLCanvasElement)n=t;else{Ne===void 0&&(Ne=es("canvas")),Ne.width=t.width,Ne.height=t.height;let s=Ne.getContext("2d");t instanceof ImageData?s.putImageData(t,0,0):s.drawImage(t,0,0,t.width,t.height),n=Ne}return n.toDataURL(e)}static sRGBToLinear(t){if(typeof HTMLImageElement<"u"&&t instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&t instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&t instanceof ImageBitmap){let e=es("canvas");e.width=t.width,e.height=t.height;let n=e.getContext("2d");n.drawImage(t,0,0,t.width,t.height);let s=n.getImageData(0,0,t.width,t.height),r=s.data;for(let o=0;o<r.length;o++)r[o]=Qt(r[o]/255)*255;return n.putImageData(s,0,0),e}else if(t.data){let e=t.data.slice(0);for(let n=0;n<e.length;n++)e instanceof Uint8Array||e instanceof Uint8ClampedArray?e[n]=Math.floor(Qt(e[n]/255)*255):e[n]=Qt(e[n]);return{data:e,width:t.width,height:t.height}}else return pt("ImageUtils.sRGBToLinear(): Unsupported image type. No color space conversion applied."),t}},Ca=0,$n=class{static{p(this,"Source")}constructor(t=null){this.isSource=!0,Object.defineProperty(this,"id",{value:Ca++}),this.uuid=ci(),this.data=t,this.dataReady=!0,this.version=0}getSize(t){let e=this.data;return typeof HTMLVideoElement<"u"&&e instanceof HTMLVideoElement?t.set(e.videoWidth,e.videoHeight,0):typeof VideoFrame<"u"&&e instanceof VideoFrame?t.set(e.displayWidth,e.displayHeight,0):e!==null?t.set(e.width,e.height,e.depth||0):t.set(0,0,0),t}set needsUpdate(t){t===!0&&this.version++}toJSON(t){let e=t===void 0||typeof t=="string";if(!e&&t.images[this.uuid]!==void 0)return t.images[this.uuid];let n={uuid:this.uuid,url:""},s=this.data;if(s!==null){let r;if(Array.isArray(s)){r=[];for(let o=0,a=s.length;o<a;o++)s[o].isDataTexture?r.push(Ii(s[o].image)):r.push(Ii(s[o]))}else r=Ii(s);n.url=r}return e||(t.images[this.uuid]=n),n}};function Ii(i){return typeof HTMLImageElement<"u"&&i instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&i instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&i instanceof ImageBitmap?qn.getDataURL(i):i.data?{data:Array.from(i.data),width:i.width,height:i.height,type:i.data.constructor.name}:(pt("Texture: Unable to serialize Texture."),{})}p(Ii,"serializeImage");var Ra=0,Pi=new V,He=class i extends ve{static{p(this,"Texture")}constructor(t=i.DEFAULT_IMAGE,e=i.DEFAULT_MAPPING,n=hn,s=hn,r=Er,o=Cr,a=Pr,c=Rr,l=i.DEFAULT_ANISOTROPY,u=xs){super(),this.isTexture=!0,Object.defineProperty(this,"id",{value:Ra++}),this.uuid=ci(),this.name="",this.source=new $n(t),this.mipmaps=[],this.mapping=e,this.channel=0,this.wrapS=n,this.wrapT=s,this.magFilter=r,this.minFilter=o,this.anisotropy=l,this.format=a,this.internalFormat=null,this.type=c,this.offset=new mt(0,0),this.repeat=new mt(1,1),this.center=new mt(0,0),this.rotation=0,this.matrixAutoUpdate=!0,this.matrix=new Y,this.generateMipmaps=!0,this.premultiplyAlpha=!1,this.flipY=!0,this.unpackAlignment=4,this.colorSpace=u,this.userData={},this.updateRanges=[],this.version=0,this.onUpdate=null,this.renderTarget=null,this.isRenderTargetTexture=!1,this.isArrayTexture=!!(t&&t.depth&&t.depth>1),this.pmremVersion=0,this.normalized=!1}get width(){return this.source.getSize(Pi).x}get height(){return this.source.getSize(Pi).y}get depth(){return this.source.getSize(Pi).z}get image(){return this.source.data}set image(t){this.source.data=t}updateMatrix(){this.matrix.setUvTransform(this.offset.x,this.offset.y,this.repeat.x,this.repeat.y,this.rotation,this.center.x,this.center.y)}addUpdateRange(t,e){this.updateRanges.push({start:t,count:e})}clearUpdateRanges(){this.updateRanges.length=0}clone(){return new this.constructor().copy(this)}copy(t){return this.name=t.name,this.source=t.source,this.mipmaps=t.mipmaps.slice(0),this.mapping=t.mapping,this.channel=t.channel,this.wrapS=t.wrapS,this.wrapT=t.wrapT,this.magFilter=t.magFilter,this.minFilter=t.minFilter,this.anisotropy=t.anisotropy,this.format=t.format,this.internalFormat=t.internalFormat,this.type=t.type,this.normalized=t.normalized,this.offset.copy(t.offset),this.repeat.copy(t.repeat),this.center.copy(t.center),this.rotation=t.rotation,this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrix.copy(t.matrix),this.generateMipmaps=t.generateMipmaps,this.premultiplyAlpha=t.premultiplyAlpha,this.flipY=t.flipY,this.unpackAlignment=t.unpackAlignment,this.colorSpace=t.colorSpace,this.renderTarget=t.renderTarget,this.isRenderTargetTexture=t.isRenderTargetTexture,this.isArrayTexture=t.isArrayTexture,this.userData=JSON.parse(JSON.stringify(t.userData)),this.needsUpdate=!0,this}setValues(t){for(let e in t){let n=t[e];if(n===void 0){pt(`Texture.setValues(): parameter '${e}' has value of undefined.`);continue}let s=this[e];if(s===void 0){pt(`Texture.setValues(): property '${e}' does not exist.`);continue}s&&n&&s.isVector2&&n.isVector2||s&&n&&s.isVector3&&n.isVector3||s&&n&&s.isMatrix3&&n.isMatrix3?s.copy(n):this[e]=n}}toJSON(t){let e=t===void 0||typeof t=="string";if(!e&&t.textures[this.uuid]!==void 0)return t.textures[this.uuid];let n={metadata:{version:4.7,type:"Texture",generator:"Texture.toJSON"},uuid:this.uuid,name:this.name,image:this.source.toJSON(t).uuid,mapping:this.mapping,channel:this.channel,repeat:[this.repeat.x,this.repeat.y],offset:[this.offset.x,this.offset.y],center:[this.center.x,this.center.y],rotation:this.rotation,wrap:[this.wrapS,this.wrapT],format:this.format,internalFormat:this.internalFormat,type:this.type,normalized:this.normalized,colorSpace:this.colorSpace,minFilter:this.minFilter,magFilter:this.magFilter,anisotropy:this.anisotropy,flipY:this.flipY,generateMipmaps:this.generateMipmaps,premultiplyAlpha:this.premultiplyAlpha,unpackAlignment:this.unpackAlignment};return Object.keys(this.userData).length>0&&(n.userData=this.userData),e||(t.textures[this.uuid]=n),n}dispose(){this.dispatchEvent({type:"dispose"})}transformUv(t){if(this.mapping!==ms)return t;if(t.applyMatrix3(this.matrix),t.x<0||t.x>1)switch(this.wrapS){case Xi:t.x=t.x-Math.floor(t.x);break;case hn:t.x=t.x<0?0:1;break;case qi:Math.abs(Math.floor(t.x)%2)===1?t.x=Math.ceil(t.x)-t.x:t.x=t.x-Math.floor(t.x);break}if(t.y<0||t.y>1)switch(this.wrapT){case Xi:t.y=t.y-Math.floor(t.y);break;case hn:t.y=t.y<0?0:1;break;case qi:Math.abs(Math.floor(t.y)%2)===1?t.y=Math.ceil(t.y)-t.y:t.y=t.y-Math.floor(t.y);break}return this.flipY&&(t.y=1-t.y),t}set needsUpdate(t){t===!0&&(this.version++,this.source.needsUpdate=!0)}set needsPMREMUpdate(t){t===!0&&this.pmremVersion++}};He.DEFAULT_IMAGE=null;He.DEFAULT_MAPPING=ms;He.DEFAULT_ANISOTROPY=1;var ns=class i{static{p(this,"Vector4")}static{i.prototype.isVector4=!0}constructor(t=0,e=0,n=0,s=1){this.x=t,this.y=e,this.z=n,this.w=s}get width(){return this.z}set width(t){this.z=t}get height(){return this.w}set height(t){this.w=t}set(t,e,n,s){return this.x=t,this.y=e,this.z=n,this.w=s,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this.w=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setW(t){return this.w=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;case 3:this.w=e;break;default:throw new Error("THREE.Vector4: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;case 3:return this.w;default:throw new Error("THREE.Vector4: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z,this.w)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this.w=t.w!==void 0?t.w:1,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this.w+=t.w,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this.w+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this.w=t.w+e.w,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this.w+=t.w*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this.w-=t.w,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this.w-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this.w=t.w-e.w,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this.w*=t.w,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this.w*=t,this}applyMatrix4(t){let e=this.x,n=this.y,s=this.z,r=this.w,o=t.elements;return this.x=o[0]*e+o[4]*n+o[8]*s+o[12]*r,this.y=o[1]*e+o[5]*n+o[9]*s+o[13]*r,this.z=o[2]*e+o[6]*n+o[10]*s+o[14]*r,this.w=o[3]*e+o[7]*n+o[11]*s+o[15]*r,this}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this.w/=t.w,this}divideScalar(t){return this.multiplyScalar(1/t)}setAxisAngleFromQuaternion(t){this.w=2*Math.acos(t.w);let e=Math.sqrt(1-t.w*t.w);return e<1e-4?(this.x=1,this.y=0,this.z=0):(this.x=t.x/e,this.y=t.y/e,this.z=t.z/e),this}setAxisAngleFromRotationMatrix(t){let e,n,s,r,c=t.elements,l=c[0],u=c[4],h=c[8],f=c[1],d=c[5],m=c[9],g=c[2],_=c[6],x=c[10];if(Math.abs(u-f)<.01&&Math.abs(h-g)<.01&&Math.abs(m-_)<.01){if(Math.abs(u+f)<.1&&Math.abs(h+g)<.1&&Math.abs(m+_)<.1&&Math.abs(l+d+x-3)<.1)return this.set(1,0,0,0),this;e=Math.PI;let v=(l+1)/2,b=(d+1)/2,S=(x+1)/2,A=(u+f)/4,M=(h+g)/4,w=(m+_)/4;return v>b&&v>S?v<.01?(n=0,s=.707106781,r=.707106781):(n=Math.sqrt(v),s=A/n,r=M/n):b>S?b<.01?(n=.707106781,s=0,r=.707106781):(s=Math.sqrt(b),n=A/s,r=w/s):S<.01?(n=.707106781,s=.707106781,r=0):(r=Math.sqrt(S),n=M/r,s=w/r),this.set(n,s,r,e),this}let y=Math.sqrt((_-m)*(_-m)+(h-g)*(h-g)+(f-u)*(f-u));return Math.abs(y)<.001&&(y=1),this.x=(_-m)/y,this.y=(h-g)/y,this.z=(f-u)/y,this.w=Math.acos((l+d+x-1)/2),this}setFromMatrixPosition(t){let e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this.w=e[15],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this.w=Math.min(this.w,t.w),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this.w=Math.max(this.w,t.w),this}clamp(t,e){return this.x=j(this.x,t.x,e.x),this.y=j(this.y,t.y,e.y),this.z=j(this.z,t.z,e.z),this.w=j(this.w,t.w,e.w),this}clampScalar(t,e){return this.x=j(this.x,t,e),this.y=j(this.y,t,e),this.z=j(this.z,t,e),this.w=j(this.w,t,e),this}clampLength(t,e){let n=this.length();return this.divideScalar(n||1).multiplyScalar(j(n,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this.w=Math.floor(this.w),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this.w=Math.ceil(this.w),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this.w=Math.round(this.w),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this.w=Math.trunc(this.w),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this.w=-this.w,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z+this.w*t.w}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)+Math.abs(this.w)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this.w+=(t.w-this.w)*e,this}lerpVectors(t,e,n){return this.x=t.x+(e.x-t.x)*n,this.y=t.y+(e.y-t.y)*n,this.z=t.z+(e.z-t.z)*n,this.w=t.w+(e.w-t.w)*n,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z&&t.w===this.w}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this.w=t[e+3],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t[e+3]=this.w,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this.w=t.getW(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this.w=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z,yield this.w}};var gt=class i{static{p(this,"Matrix4")}static{i.prototype.isMatrix4=!0}constructor(t,e,n,s,r,o,a,c,l,u,h,f,d,m,g,_){this.elements=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],t!==void 0&&this.set(t,e,n,s,r,o,a,c,l,u,h,f,d,m,g,_)}set(t,e,n,s,r,o,a,c,l,u,h,f,d,m,g,_){let x=this.elements;return x[0]=t,x[4]=e,x[8]=n,x[12]=s,x[1]=r,x[5]=o,x[9]=a,x[13]=c,x[2]=l,x[6]=u,x[10]=h,x[14]=f,x[3]=d,x[7]=m,x[11]=g,x[15]=_,this}identity(){return this.set(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),this}clone(){return new i().fromArray(this.elements)}copy(t){let e=this.elements,n=t.elements;return e[0]=n[0],e[1]=n[1],e[2]=n[2],e[3]=n[3],e[4]=n[4],e[5]=n[5],e[6]=n[6],e[7]=n[7],e[8]=n[8],e[9]=n[9],e[10]=n[10],e[11]=n[11],e[12]=n[12],e[13]=n[13],e[14]=n[14],e[15]=n[15],this}copyPosition(t){let e=this.elements,n=t.elements;return e[12]=n[12],e[13]=n[13],e[14]=n[14],this}setFromMatrix3(t){let e=t.elements;return this.set(e[0],e[3],e[6],0,e[1],e[4],e[7],0,e[2],e[5],e[8],0,0,0,0,1),this}extractBasis(t,e,n){return this.determinantAffine()===0?(t.set(1,0,0),e.set(0,1,0),n.set(0,0,1),this):(t.setFromMatrixColumn(this,0),e.setFromMatrixColumn(this,1),n.setFromMatrixColumn(this,2),this)}makeBasis(t,e,n){return this.set(t.x,e.x,n.x,0,t.y,e.y,n.y,0,t.z,e.z,n.z,0,0,0,0,1),this}extractRotation(t){if(t.determinantAffine()===0)return this.identity();let e=this.elements,n=t.elements,s=1/De.setFromMatrixColumn(t,0).length(),r=1/De.setFromMatrixColumn(t,1).length(),o=1/De.setFromMatrixColumn(t,2).length();return e[0]=n[0]*s,e[1]=n[1]*s,e[2]=n[2]*s,e[3]=0,e[4]=n[4]*r,e[5]=n[5]*r,e[6]=n[6]*r,e[7]=0,e[8]=n[8]*o,e[9]=n[9]*o,e[10]=n[10]*o,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromEuler(t){let e=this.elements,n=t.x,s=t.y,r=t.z,o=Math.cos(n),a=Math.sin(n),c=Math.cos(s),l=Math.sin(s),u=Math.cos(r),h=Math.sin(r);if(t.order==="XYZ"){let f=o*u,d=o*h,m=a*u,g=a*h;e[0]=c*u,e[4]=-c*h,e[8]=l,e[1]=d+m*l,e[5]=f-g*l,e[9]=-a*c,e[2]=g-f*l,e[6]=m+d*l,e[10]=o*c}else if(t.order==="YXZ"){let f=c*u,d=c*h,m=l*u,g=l*h;e[0]=f+g*a,e[4]=m*a-d,e[8]=o*l,e[1]=o*h,e[5]=o*u,e[9]=-a,e[2]=d*a-m,e[6]=g+f*a,e[10]=o*c}else if(t.order==="ZXY"){let f=c*u,d=c*h,m=l*u,g=l*h;e[0]=f-g*a,e[4]=-o*h,e[8]=m+d*a,e[1]=d+m*a,e[5]=o*u,e[9]=g-f*a,e[2]=-o*l,e[6]=a,e[10]=o*c}else if(t.order==="ZYX"){let f=o*u,d=o*h,m=a*u,g=a*h;e[0]=c*u,e[4]=m*l-d,e[8]=f*l+g,e[1]=c*h,e[5]=g*l+f,e[9]=d*l-m,e[2]=-l,e[6]=a*c,e[10]=o*c}else if(t.order==="YZX"){let f=o*c,d=o*l,m=a*c,g=a*l;e[0]=c*u,e[4]=g-f*h,e[8]=m*h+d,e[1]=h,e[5]=o*u,e[9]=-a*u,e[2]=-l*u,e[6]=d*h+m,e[10]=f-g*h}else if(t.order==="XZY"){let f=o*c,d=o*l,m=a*c,g=a*l;e[0]=c*u,e[4]=-h,e[8]=l*u,e[1]=f*h+g,e[5]=o*u,e[9]=d*h-m,e[2]=m*h-d,e[6]=a*u,e[10]=g*h+f}return e[3]=0,e[7]=0,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromQuaternion(t){return this.compose(Ia,t,Pa)}lookAt(t,e,n){let s=this.elements;return Pt.subVectors(t,e),Pt.lengthSq()===0&&(Pt.z=1),Pt.normalize(),re.crossVectors(n,Pt),re.lengthSq()===0&&(Math.abs(n.z)===1?Pt.x+=1e-4:Pt.z+=1e-4,Pt.normalize(),re.crossVectors(n,Pt)),re.normalize(),Ln.crossVectors(Pt,re),s[0]=re.x,s[4]=Ln.x,s[8]=Pt.x,s[1]=re.y,s[5]=Ln.y,s[9]=Pt.y,s[2]=re.z,s[6]=Ln.z,s[10]=Pt.z,this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){let n=t.elements,s=e.elements,r=this.elements,o=n[0],a=n[4],c=n[8],l=n[12],u=n[1],h=n[5],f=n[9],d=n[13],m=n[2],g=n[6],_=n[10],x=n[14],y=n[3],v=n[7],b=n[11],S=n[15],A=s[0],M=s[4],w=s[8],I=s[12],E=s[1],L=s[5],D=s[9],R=s[13],C=s[2],P=s[6],T=s[10],U=s[14],F=s[3],N=s[7],O=s[11],k=s[15];return r[0]=o*A+a*E+c*C+l*F,r[4]=o*M+a*L+c*P+l*N,r[8]=o*w+a*D+c*T+l*O,r[12]=o*I+a*R+c*U+l*k,r[1]=u*A+h*E+f*C+d*F,r[5]=u*M+h*L+f*P+d*N,r[9]=u*w+h*D+f*T+d*O,r[13]=u*I+h*R+f*U+d*k,r[2]=m*A+g*E+_*C+x*F,r[6]=m*M+g*L+_*P+x*N,r[10]=m*w+g*D+_*T+x*O,r[14]=m*I+g*R+_*U+x*k,r[3]=y*A+v*E+b*C+S*F,r[7]=y*M+v*L+b*P+S*N,r[11]=y*w+v*D+b*T+S*O,r[15]=y*I+v*R+b*U+S*k,this}multiplyScalar(t){let e=this.elements;return e[0]*=t,e[4]*=t,e[8]*=t,e[12]*=t,e[1]*=t,e[5]*=t,e[9]*=t,e[13]*=t,e[2]*=t,e[6]*=t,e[10]*=t,e[14]*=t,e[3]*=t,e[7]*=t,e[11]*=t,e[15]*=t,this}determinant(){let t=this.elements,e=t[0],n=t[4],s=t[8],r=t[12],o=t[1],a=t[5],c=t[9],l=t[13],u=t[2],h=t[6],f=t[10],d=t[14],m=t[3],g=t[7],_=t[11],x=t[15],y=c*d-l*f,v=a*d-l*h,b=a*f-c*h,S=o*d-l*u,A=o*f-c*u,M=o*h-a*u;return e*(g*y-_*v+x*b)-n*(m*y-_*S+x*A)+s*(m*v-g*S+x*M)-r*(m*b-g*A+_*M)}determinantAffine(){let t=this.elements,e=t[0],n=t[4],s=t[8],r=t[1],o=t[5],a=t[9],c=t[2],l=t[6],u=t[10];return e*(o*u-a*l)-n*(r*u-a*c)+s*(r*l-o*c)}transpose(){let t=this.elements,e;return e=t[1],t[1]=t[4],t[4]=e,e=t[2],t[2]=t[8],t[8]=e,e=t[6],t[6]=t[9],t[9]=e,e=t[3],t[3]=t[12],t[12]=e,e=t[7],t[7]=t[13],t[13]=e,e=t[11],t[11]=t[14],t[14]=e,this}setPosition(t,e,n){let s=this.elements;return t.isVector3?(s[12]=t.x,s[13]=t.y,s[14]=t.z):(s[12]=t,s[13]=e,s[14]=n),this}invert(){let t=this.elements,e=t[0],n=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8],h=t[9],f=t[10],d=t[11],m=t[12],g=t[13],_=t[14],x=t[15],y=e*a-n*o,v=e*c-s*o,b=e*l-r*o,S=n*c-s*a,A=n*l-r*a,M=s*l-r*c,w=u*g-h*m,I=u*_-f*m,E=u*x-d*m,L=h*_-f*g,D=h*x-d*g,R=f*x-d*_,C=y*R-v*D+b*L+S*E-A*I+M*w;if(C===0)return this.set(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0);let P=1/C;return t[0]=(a*R-c*D+l*L)*P,t[1]=(s*D-n*R-r*L)*P,t[2]=(g*M-_*A+x*S)*P,t[3]=(f*A-h*M-d*S)*P,t[4]=(c*E-o*R-l*I)*P,t[5]=(e*R-s*E+r*I)*P,t[6]=(_*b-m*M-x*v)*P,t[7]=(u*M-f*b+d*v)*P,t[8]=(o*D-a*E+l*w)*P,t[9]=(n*E-e*D-r*w)*P,t[10]=(m*A-g*b+x*y)*P,t[11]=(h*b-u*A-d*y)*P,t[12]=(a*I-o*L-c*w)*P,t[13]=(e*L-n*I+s*w)*P,t[14]=(g*v-m*S-_*y)*P,t[15]=(u*S-h*v+f*y)*P,this}scale(t){let e=this.elements,n=t.x,s=t.y,r=t.z;return e[0]*=n,e[4]*=s,e[8]*=r,e[1]*=n,e[5]*=s,e[9]*=r,e[2]*=n,e[6]*=s,e[10]*=r,e[3]*=n,e[7]*=s,e[11]*=r,this}getMaxScaleOnAxis(){let t=this.elements,e=t[0]*t[0]+t[1]*t[1]+t[2]*t[2],n=t[4]*t[4]+t[5]*t[5]+t[6]*t[6],s=t[8]*t[8]+t[9]*t[9]+t[10]*t[10];return Math.sqrt(Math.max(e,n,s))}makeTranslation(t,e,n){return t.isVector3?this.set(1,0,0,t.x,0,1,0,t.y,0,0,1,t.z,0,0,0,1):this.set(1,0,0,t,0,1,0,e,0,0,1,n,0,0,0,1),this}makeRotationX(t){let e=Math.cos(t),n=Math.sin(t);return this.set(1,0,0,0,0,e,-n,0,0,n,e,0,0,0,0,1),this}makeRotationY(t){let e=Math.cos(t),n=Math.sin(t);return this.set(e,0,n,0,0,1,0,0,-n,0,e,0,0,0,0,1),this}makeRotationZ(t){let e=Math.cos(t),n=Math.sin(t);return this.set(e,-n,0,0,n,e,0,0,0,0,1,0,0,0,0,1),this}makeRotationAxis(t,e){let n=Math.cos(e),s=Math.sin(e),r=1-n,o=t.x,a=t.y,c=t.z,l=r*o,u=r*a;return this.set(l*o+n,l*a-s*c,l*c+s*a,0,l*a+s*c,u*a+n,u*c-s*o,0,l*c-s*a,u*c+s*o,r*c*c+n,0,0,0,0,1),this}makeScale(t,e,n){return this.set(t,0,0,0,0,e,0,0,0,0,n,0,0,0,0,1),this}makeShear(t,e,n,s,r,o){return this.set(1,n,r,0,t,1,o,0,e,s,1,0,0,0,0,1),this}compose(t,e,n){let s=this.elements,r=e._x,o=e._y,a=e._z,c=e._w,l=r+r,u=o+o,h=a+a,f=r*l,d=r*u,m=r*h,g=o*u,_=o*h,x=a*h,y=c*l,v=c*u,b=c*h,S=n.x,A=n.y,M=n.z;return s[0]=(1-(g+x))*S,s[1]=(d+b)*S,s[2]=(m-v)*S,s[3]=0,s[4]=(d-b)*A,s[5]=(1-(f+x))*A,s[6]=(_+y)*A,s[7]=0,s[8]=(m+v)*M,s[9]=(_-y)*M,s[10]=(1-(f+g))*M,s[11]=0,s[12]=t.x,s[13]=t.y,s[14]=t.z,s[15]=1,this}decompose(t,e,n){let s=this.elements;t.x=s[12],t.y=s[13],t.z=s[14];let r=this.determinantAffine();if(r===0)return n.set(1,1,1),e.identity(),this;let o=De.set(s[0],s[1],s[2]).length(),a=De.set(s[4],s[5],s[6]).length(),c=De.set(s[8],s[9],s[10]).length();r<0&&(o=-o),Xt.copy(this);let l=1/o,u=1/a,h=1/c;return Xt.elements[0]*=l,Xt.elements[1]*=l,Xt.elements[2]*=l,Xt.elements[4]*=u,Xt.elements[5]*=u,Xt.elements[6]*=u,Xt.elements[8]*=h,Xt.elements[9]*=h,Xt.elements[10]*=h,e.setFromRotationMatrix(Xt),n.x=o,n.y=a,n.z=c,this}makePerspective(t,e,n,s,r,o,a=fn,c=!1){let l=this.elements,u=2*r/(e-t),h=2*r/(n-s),f=(e+t)/(e-t),d=(n+s)/(n-s),m,g;if(c)m=r/(o-r),g=o*r/(o-r);else if(a===fn)m=-(o+r)/(o-r),g=-2*o*r/(o-r);else if(a===ts)m=-o/(o-r),g=-o*r/(o-r);else throw new Error("THREE.Matrix4.makePerspective(): Invalid coordinate system: "+a);return l[0]=u,l[4]=0,l[8]=f,l[12]=0,l[1]=0,l[5]=h,l[9]=d,l[13]=0,l[2]=0,l[6]=0,l[10]=m,l[14]=g,l[3]=0,l[7]=0,l[11]=-1,l[15]=0,this}makeOrthographic(t,e,n,s,r,o,a=fn,c=!1){let l=this.elements,u=2/(e-t),h=2/(n-s),f=-(e+t)/(e-t),d=-(n+s)/(n-s),m,g;if(c)m=1/(o-r),g=o/(o-r);else if(a===fn)m=-2/(o-r),g=-(o+r)/(o-r);else if(a===ts)m=-1/(o-r),g=-r/(o-r);else throw new Error("THREE.Matrix4.makeOrthographic(): Invalid coordinate system: "+a);return l[0]=u,l[4]=0,l[8]=0,l[12]=f,l[1]=0,l[5]=h,l[9]=0,l[13]=d,l[2]=0,l[6]=0,l[10]=m,l[14]=g,l[3]=0,l[7]=0,l[11]=0,l[15]=1,this}equals(t){let e=this.elements,n=t.elements;for(let s=0;s<16;s++)if(e[s]!==n[s])return!1;return!0}fromArray(t,e=0){for(let n=0;n<16;n++)this.elements[n]=t[n+e];return this}toArray(t=[],e=0){let n=this.elements;return t[e]=n[0],t[e+1]=n[1],t[e+2]=n[2],t[e+3]=n[3],t[e+4]=n[4],t[e+5]=n[5],t[e+6]=n[6],t[e+7]=n[7],t[e+8]=n[8],t[e+9]=n[9],t[e+10]=n[10],t[e+11]=n[11],t[e+12]=n[12],t[e+13]=n[13],t[e+14]=n[14],t[e+15]=n[15],t}},De=new V,Xt=new gt,Ia=new V(0,0,0),Pa=new V(1,1,1),re=new V,Ln=new V,Pt=new V,lr=new gt,ur=new $t,mn=class i{static{p(this,"Euler")}constructor(t=0,e=0,n=0,s=i.DEFAULT_ORDER){this.isEuler=!0,this._x=t,this._y=e,this._z=n,this._order=s}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get order(){return this._order}set order(t){this._order=t,this._onChangeCallback()}set(t,e,n,s=this._order){return this._x=t,this._y=e,this._z=n,this._order=s,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._order)}copy(t){return this._x=t._x,this._y=t._y,this._z=t._z,this._order=t._order,this._onChangeCallback(),this}setFromRotationMatrix(t,e=this._order,n=!0){let s=t.elements,r=s[0],o=s[4],a=s[8],c=s[1],l=s[5],u=s[9],h=s[2],f=s[6],d=s[10];switch(e){case"XYZ":this._y=Math.asin(j(a,-1,1)),Math.abs(a)<.9999999?(this._x=Math.atan2(-u,d),this._z=Math.atan2(-o,r)):(this._x=Math.atan2(f,l),this._z=0);break;case"YXZ":this._x=Math.asin(-j(u,-1,1)),Math.abs(u)<.9999999?(this._y=Math.atan2(a,d),this._z=Math.atan2(c,l)):(this._y=Math.atan2(-h,r),this._z=0);break;case"ZXY":this._x=Math.asin(j(f,-1,1)),Math.abs(f)<.9999999?(this._y=Math.atan2(-h,d),this._z=Math.atan2(-o,l)):(this._y=0,this._z=Math.atan2(c,r));break;case"ZYX":this._y=Math.asin(-j(h,-1,1)),Math.abs(h)<.9999999?(this._x=Math.atan2(f,d),this._z=Math.atan2(c,r)):(this._x=0,this._z=Math.atan2(-o,l));break;case"YZX":this._z=Math.asin(j(c,-1,1)),Math.abs(c)<.9999999?(this._x=Math.atan2(-u,l),this._y=Math.atan2(-h,r)):(this._x=0,this._y=Math.atan2(a,d));break;case"XZY":this._z=Math.asin(-j(o,-1,1)),Math.abs(o)<.9999999?(this._x=Math.atan2(f,l),this._y=Math.atan2(a,r)):(this._x=Math.atan2(-u,d),this._y=0);break;default:pt("Euler: .setFromRotationMatrix() encountered an unknown order: "+e)}return this._order=e,n===!0&&this._onChangeCallback(),this}setFromQuaternion(t,e,n){return lr.makeRotationFromQuaternion(t),this.setFromRotationMatrix(lr,e,n)}setFromVector3(t,e=this._order){return this.set(t.x,t.y,t.z,e)}reorder(t){return ur.setFromEuler(this),this.setFromQuaternion(ur,t)}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._order===this._order}fromArray(t){return this._x=t[0],this._y=t[1],this._z=t[2],t[3]!==void 0&&(this._order=t[3]),this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._order,t}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._order}};mn.DEFAULT_ORDER="XYZ";var Yn=class{static{p(this,"Layers")}constructor(){this.mask=1}set(t){this.mask=(1<<t|0)>>>0}enable(t){this.mask|=1<<t|0}enableAll(){this.mask=-1}toggle(t){this.mask^=1<<t|0}disable(t){this.mask&=~(1<<t|0)}disableAll(){this.mask=0}test(t){return(this.mask&t.mask)!==0}isEnabled(t){return(this.mask&(1<<t|0))!==0}},La=0,hr=new V,Ue=new $t,Kt=new gt,Nn=new V,an=new V,Na=new V,Da=new $t,fr=new V(1,0,0),dr=new V(0,1,0),pr=new V(0,0,1),mr={type:"added"},Ua={type:"removed"},Fe={type:"childadded",child:null},Li={type:"childremoved",child:null},Me=class i extends ve{static{p(this,"Object3D")}constructor(){super(),this.isObject3D=!0,Object.defineProperty(this,"id",{value:La++}),this.uuid=ci(),this.name="",this.type="Object3D",this.parent=null,this.children=[],this.up=i.DEFAULT_UP.clone();let t=new V,e=new mn,n=new $t,s=new V(1,1,1);function r(){n.setFromEuler(e,!1)}p(r,"onRotationChange");function o(){e.setFromQuaternion(n,void 0,!1)}p(o,"onQuaternionChange"),e._onChange(r),n._onChange(o),Object.defineProperties(this,{position:{configurable:!0,enumerable:!0,value:t},rotation:{configurable:!0,enumerable:!0,value:e},quaternion:{configurable:!0,enumerable:!0,value:n},scale:{configurable:!0,enumerable:!0,value:s},modelViewMatrix:{value:new gt},normalMatrix:{value:new Y}}),this.matrix=new gt,this.matrixWorld=new gt,this.matrixAutoUpdate=i.DEFAULT_MATRIX_AUTO_UPDATE,this.matrixWorldAutoUpdate=i.DEFAULT_MATRIX_WORLD_AUTO_UPDATE,this.matrixWorldNeedsUpdate=!1,this.layers=new Yn,this.visible=!0,this.castShadow=!1,this.receiveShadow=!1,this.frustumCulled=!0,this.renderOrder=0,this.animations=[],this.customDepthMaterial=void 0,this.customDistanceMaterial=void 0,this.static=!1,this.userData={},this.pivot=null}onBeforeShadow(){}onAfterShadow(){}onBeforeRender(){}onAfterRender(){}applyMatrix4(t){this.matrixAutoUpdate&&this.updateMatrix(),this.matrix.premultiply(t),this.matrix.decompose(this.position,this.quaternion,this.scale)}applyQuaternion(t){return this.quaternion.premultiply(t),this}setRotationFromAxisAngle(t,e){this.quaternion.setFromAxisAngle(t,e)}setRotationFromEuler(t){this.quaternion.setFromEuler(t,!0)}setRotationFromMatrix(t){this.quaternion.setFromRotationMatrix(t)}setRotationFromQuaternion(t){this.quaternion.copy(t)}rotateOnAxis(t,e){return Ue.setFromAxisAngle(t,e),this.quaternion.multiply(Ue),this}rotateOnWorldAxis(t,e){return Ue.setFromAxisAngle(t,e),this.quaternion.premultiply(Ue),this}rotateX(t){return this.rotateOnAxis(fr,t)}rotateY(t){return this.rotateOnAxis(dr,t)}rotateZ(t){return this.rotateOnAxis(pr,t)}translateOnAxis(t,e){return hr.copy(t).applyQuaternion(this.quaternion),this.position.add(hr.multiplyScalar(e)),this}translateX(t){return this.translateOnAxis(fr,t)}translateY(t){return this.translateOnAxis(dr,t)}translateZ(t){return this.translateOnAxis(pr,t)}localToWorld(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(this.matrixWorld)}worldToLocal(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(Kt.copy(this.matrixWorld).invert())}lookAt(t,e,n){t.isVector3?Nn.copy(t):Nn.set(t,e,n);let s=this.parent;this.updateWorldMatrix(!0,!1),an.setFromMatrixPosition(this.matrixWorld),this.isCamera||this.isLight?Kt.lookAt(an,Nn,this.up):Kt.lookAt(Nn,an,this.up),this.quaternion.setFromRotationMatrix(Kt),s&&(Kt.extractRotation(s.matrixWorld),Ue.setFromRotationMatrix(Kt),this.quaternion.premultiply(Ue.invert()))}add(t){if(arguments.length>1){for(let e=0;e<arguments.length;e++)this.add(arguments[e]);return this}return t===this?(ot("Object3D.add: object can't be added as a child of itself.",t),this):(t&&t.isObject3D?(t.removeFromParent(),t.parent=this,this.children.push(t),t.dispatchEvent(mr),Fe.child=t,this.dispatchEvent(Fe),Fe.child=null):ot("Object3D.add: object not an instance of THREE.Object3D.",t),this)}remove(t){if(arguments.length>1){for(let n=0;n<arguments.length;n++)this.remove(arguments[n]);return this}let e=this.children.indexOf(t);return e!==-1&&(t.parent=null,this.children.splice(e,1),t.dispatchEvent(Ua),Li.child=t,this.dispatchEvent(Li),Li.child=null),this}removeFromParent(){let t=this.parent;return t!==null&&t.remove(this),this}clear(){return this.remove(...this.children)}attach(t){return this.updateWorldMatrix(!0,!1),Kt.copy(this.matrixWorld).invert(),t.parent!==null&&(t.parent.updateWorldMatrix(!0,!1),Kt.multiply(t.parent.matrixWorld)),t.applyMatrix4(Kt),t.removeFromParent(),t.parent=this,this.children.push(t),t.updateWorldMatrix(!1,!0),t.dispatchEvent(mr),Fe.child=t,this.dispatchEvent(Fe),Fe.child=null,this}getObjectById(t){return this.getObjectByProperty("id",t)}getObjectByName(t){return this.getObjectByProperty("name",t)}getObjectByProperty(t,e){if(this[t]===e)return this;for(let n=0,s=this.children.length;n<s;n++){let o=this.children[n].getObjectByProperty(t,e);if(o!==void 0)return o}}getObjectsByProperty(t,e,n=[]){this[t]===e&&n.push(this);let s=this.children;for(let r=0,o=s.length;r<o;r++)s[r].getObjectsByProperty(t,e,n);return n}getWorldPosition(t){return this.updateWorldMatrix(!0,!1),t.setFromMatrixPosition(this.matrixWorld)}getWorldQuaternion(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(an,t,Na),t}getWorldScale(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(an,Da,t),t}getWorldDirection(t){this.updateWorldMatrix(!0,!1);let e=this.matrixWorld.elements;return t.set(e[8],e[9],e[10]).normalize()}raycast(){}traverse(t){t(this);let e=this.children;for(let n=0,s=e.length;n<s;n++)e[n].traverse(t)}traverseVisible(t){if(this.visible===!1)return;t(this);let e=this.children;for(let n=0,s=e.length;n<s;n++)e[n].traverseVisible(t)}traverseAncestors(t){let e=this.parent;e!==null&&(t(e),e.traverseAncestors(t))}updateMatrix(){this.matrix.compose(this.position,this.quaternion,this.scale);let t=this.pivot;if(t!==null){let e=t.x,n=t.y,s=t.z,r=this.matrix.elements;r[12]+=e-r[0]*e-r[4]*n-r[8]*s,r[13]+=n-r[1]*e-r[5]*n-r[9]*s,r[14]+=s-r[2]*e-r[6]*n-r[10]*s}this.matrixWorldNeedsUpdate=!0}updateMatrixWorld(t){this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||t)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,t=!0);let e=this.children;for(let n=0,s=e.length;n<s;n++)e[n].updateMatrixWorld(t)}updateWorldMatrix(t,e,n=!1){let s=this.parent;if(t===!0&&s!==null&&s.updateWorldMatrix(!0,!1),this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||n)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,n=!0),e===!0){let r=this.children;for(let o=0,a=r.length;o<a;o++)r[o].updateWorldMatrix(!1,!0,n)}}toJSON(t){let e=t===void 0||typeof t=="string",n={};e&&(t={geometries:{},materials:{},textures:{},images:{},shapes:{},skeletons:{},animations:{},nodes:{}},n.metadata={version:4.7,type:"Object",generator:"Object3D.toJSON"});let s={};s.uuid=this.uuid,s.type=this.type,this.name!==""&&(s.name=this.name),this.castShadow===!0&&(s.castShadow=!0),this.receiveShadow===!0&&(s.receiveShadow=!0),this.visible===!1&&(s.visible=!1),this.frustumCulled===!1&&(s.frustumCulled=!1),this.renderOrder!==0&&(s.renderOrder=this.renderOrder),this.static!==!1&&(s.static=this.static),Object.keys(this.userData).length>0&&(s.userData=this.userData),s.layers=this.layers.mask,s.matrix=this.matrix.toArray(),s.up=this.up.toArray(),this.pivot!==null&&(s.pivot=this.pivot.toArray()),this.matrixAutoUpdate===!1&&(s.matrixAutoUpdate=!1),this.morphTargetDictionary!==void 0&&(s.morphTargetDictionary=Object.assign({},this.morphTargetDictionary)),this.morphTargetInfluences!==void 0&&(s.morphTargetInfluences=this.morphTargetInfluences.slice()),this.isInstancedMesh&&(s.type="InstancedMesh",s.count=this.count,s.instanceMatrix=this.instanceMatrix.toJSON(),this.instanceColor!==null&&(s.instanceColor=this.instanceColor.toJSON())),this.isBatchedMesh&&(s.type="BatchedMesh",s.perObjectFrustumCulled=this.perObjectFrustumCulled,s.sortObjects=this.sortObjects,s.drawRanges=this._drawRanges,s.reservedRanges=this._reservedRanges,s.geometryInfo=this._geometryInfo.map(a=>({...a,boundingBox:a.boundingBox?a.boundingBox.toJSON():void 0,boundingSphere:a.boundingSphere?a.boundingSphere.toJSON():void 0})),s.instanceInfo=this._instanceInfo.map(a=>({...a})),s.availableInstanceIds=this._availableInstanceIds.slice(),s.availableGeometryIds=this._availableGeometryIds.slice(),s.nextIndexStart=this._nextIndexStart,s.nextVertexStart=this._nextVertexStart,s.geometryCount=this._geometryCount,s.maxInstanceCount=this._maxInstanceCount,s.maxVertexCount=this._maxVertexCount,s.maxIndexCount=this._maxIndexCount,s.geometryInitialized=this._geometryInitialized,s.matricesTexture=this._matricesTexture.toJSON(t),s.indirectTexture=this._indirectTexture.toJSON(t),this._colorsTexture!==null&&(s.colorsTexture=this._colorsTexture.toJSON(t)),this.boundingSphere!==null&&(s.boundingSphere=this.boundingSphere.toJSON()),this.boundingBox!==null&&(s.boundingBox=this.boundingBox.toJSON()));function r(a,c){return a[c.uuid]===void 0&&(a[c.uuid]=c.toJSON(t)),c.uuid}if(p(r,"serialize"),this.isScene)this.background&&(this.background.isColor?s.background=this.background.toJSON():this.background.isTexture&&(s.background=this.background.toJSON(t).uuid)),this.environment&&this.environment.isTexture&&this.environment.isRenderTargetTexture!==!0&&(s.environment=this.environment.toJSON(t).uuid);else if(this.isMesh||this.isLine||this.isPoints){s.geometry=r(t.geometries,this.geometry);let a=this.geometry.parameters;if(a!==void 0&&a.shapes!==void 0){let c=a.shapes;if(Array.isArray(c))for(let l=0,u=c.length;l<u;l++){let h=c[l];r(t.shapes,h)}else r(t.shapes,c)}}if(this.isSkinnedMesh&&(s.bindMode=this.bindMode,s.bindMatrix=this.bindMatrix.toArray(),this.skeleton!==void 0&&(r(t.skeletons,this.skeleton),s.skeleton=this.skeleton.uuid)),this.material!==void 0)if(Array.isArray(this.material)){let a=[];for(let c=0,l=this.material.length;c<l;c++)a.push(r(t.materials,this.material[c]));s.material=a}else s.material=r(t.materials,this.material);if(this.children.length>0){s.children=[];for(let a=0;a<this.children.length;a++)s.children.push(this.children[a].toJSON(t).object)}if(this.animations.length>0){s.animations=[];for(let a=0;a<this.animations.length;a++){let c=this.animations[a];s.animations.push(r(t.animations,c))}}if(e){let a=o(t.geometries),c=o(t.materials),l=o(t.textures),u=o(t.images),h=o(t.shapes),f=o(t.skeletons),d=o(t.animations),m=o(t.nodes);a.length>0&&(n.geometries=a),c.length>0&&(n.materials=c),l.length>0&&(n.textures=l),u.length>0&&(n.images=u),h.length>0&&(n.shapes=h),f.length>0&&(n.skeletons=f),d.length>0&&(n.animations=d),m.length>0&&(n.nodes=m)}return n.object=s,n;function o(a){let c=[];for(let l in a){let u=a[l];delete u.metadata,c.push(u)}return c}p(o,"extractFromCache")}clone(t){return new this.constructor().copy(this,t)}copy(t,e=!0){if(this.name=t.name,this.up.copy(t.up),this.position.copy(t.position),this.rotation.order=t.rotation.order,this.quaternion.copy(t.quaternion),this.scale.copy(t.scale),this.pivot=t.pivot!==null?t.pivot.clone():null,this.matrix.copy(t.matrix),this.matrixWorld.copy(t.matrixWorld),this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrixWorldAutoUpdate=t.matrixWorldAutoUpdate,this.matrixWorldNeedsUpdate=t.matrixWorldNeedsUpdate,this.layers.mask=t.layers.mask,this.visible=t.visible,this.castShadow=t.castShadow,this.receiveShadow=t.receiveShadow,this.frustumCulled=t.frustumCulled,this.renderOrder=t.renderOrder,this.static=t.static,this.animations=t.animations.slice(),this.userData=JSON.parse(JSON.stringify(t.userData)),e===!0)for(let n=0;n<t.children.length;n++){let s=t.children[n];this.add(s.clone())}return this}};Me.DEFAULT_UP=new V(0,1,0);Me.DEFAULT_MATRIX_AUTO_UPDATE=!0;Me.DEFAULT_MATRIX_WORLD_AUTO_UPDATE=!0;var Nr={aliceblue:15792383,antiquewhite:16444375,aqua:65535,aquamarine:8388564,azure:15794175,beige:16119260,bisque:16770244,black:0,blanchedalmond:16772045,blue:255,blueviolet:9055202,brown:10824234,burlywood:14596231,cadetblue:6266528,chartreuse:8388352,chocolate:13789470,coral:16744272,cornflowerblue:6591981,cornsilk:16775388,crimson:14423100,cyan:65535,darkblue:139,darkcyan:35723,darkgoldenrod:12092939,darkgray:11119017,darkgreen:25600,darkgrey:11119017,darkkhaki:12433259,darkmagenta:9109643,darkolivegreen:5597999,darkorange:16747520,darkorchid:10040012,darkred:9109504,darksalmon:15308410,darkseagreen:9419919,darkslateblue:4734347,darkslategray:3100495,darkslategrey:3100495,darkturquoise:52945,darkviolet:9699539,deeppink:16716947,deepskyblue:49151,dimgray:6908265,dimgrey:6908265,dodgerblue:2003199,firebrick:11674146,floralwhite:16775920,forestgreen:2263842,fuchsia:16711935,gainsboro:14474460,ghostwhite:16316671,gold:16766720,goldenrod:14329120,gray:8421504,green:32768,greenyellow:11403055,grey:8421504,honeydew:15794160,hotpink:16738740,indianred:13458524,indigo:4915330,ivory:16777200,khaki:15787660,lavender:15132410,lavenderblush:16773365,lawngreen:8190976,lemonchiffon:16775885,lightblue:11393254,lightcoral:15761536,lightcyan:14745599,lightgoldenrodyellow:16448210,lightgray:13882323,lightgreen:9498256,lightgrey:13882323,lightpink:16758465,lightsalmon:16752762,lightseagreen:2142890,lightskyblue:8900346,lightslategray:7833753,lightslategrey:7833753,lightsteelblue:11584734,lightyellow:16777184,lime:65280,limegreen:3329330,linen:16445670,magenta:16711935,maroon:8388608,mediumaquamarine:6737322,mediumblue:205,mediumorchid:12211667,mediumpurple:9662683,mediumseagreen:3978097,mediumslateblue:8087790,mediumspringgreen:64154,mediumturquoise:4772300,mediumvioletred:13047173,midnightblue:1644912,mintcream:16121850,mistyrose:16770273,moccasin:16770229,navajowhite:16768685,navy:128,oldlace:16643558,olive:8421376,olivedrab:7048739,orange:16753920,orangered:16729344,orchid:14315734,palegoldenrod:15657130,palegreen:10025880,paleturquoise:11529966,palevioletred:14381203,papayawhip:16773077,peachpuff:16767673,peru:13468991,pink:16761035,plum:14524637,powderblue:11591910,purple:8388736,rebeccapurple:6697881,red:16711680,rosybrown:12357519,royalblue:4286945,saddlebrown:9127187,salmon:16416882,sandybrown:16032864,seagreen:3050327,seashell:16774638,sienna:10506797,silver:12632256,skyblue:8900331,slateblue:6970061,slategray:7372944,slategrey:7372944,snow:16775930,springgreen:65407,steelblue:4620980,tan:13808780,teal:32896,thistle:14204888,tomato:16737095,turquoise:4251856,violet:15631086,wheat:16113331,white:16777215,whitesmoke:16119285,yellow:16776960,yellowgreen:10145074},oe={h:0,s:0,l:0},Dn={h:0,s:0,l:0};function Ni(i,t,e){return e<0&&(e+=1),e>1&&(e-=1),e<1/6?i+(t-i)*6*e:e<1/2?t:e<2/3?i+(t-i)*6*(2/3-e):i}p(Ni,"hue2rgb");var xt=class{static{p(this,"Color")}constructor(t,e,n){return this.isColor=!0,this.r=1,this.g=1,this.b=1,this.set(t,e,n)}set(t,e,n){if(e===void 0&&n===void 0){let s=t;s&&s.isColor?this.copy(s):typeof s=="number"?this.setHex(s):typeof s=="string"&&this.setStyle(s)}else this.setRGB(t,e,n);return this}setScalar(t){return this.r=t,this.g=t,this.b=t,this}setHex(t,e=kt){return t=Math.floor(t),this.r=(t>>16&255)/255,this.g=(t>>8&255)/255,this.b=(t&255)/255,zt.colorSpaceToWorking(this,e),this}setRGB(t,e,n,s=zt.workingColorSpace){return this.r=t,this.g=e,this.b=n,zt.colorSpaceToWorking(this,s),this}setHSL(t,e,n,s=zt.workingColorSpace){if(t=Ta(t,1),e=j(e,0,1),n=j(n,0,1),e===0)this.r=this.g=this.b=n;else{let r=n<=.5?n*(1+e):n+e-n*e,o=2*n-r;this.r=Ni(o,r,t+1/3),this.g=Ni(o,r,t),this.b=Ni(o,r,t-1/3)}return zt.colorSpaceToWorking(this,s),this}setStyle(t,e=kt){function n(r){r!==void 0&&parseFloat(r)<1&&pt("Color: Alpha component of "+t+" will be ignored.")}p(n,"handleAlpha");let s;if(s=/^(\w+)\(([^\)]*)\)/.exec(t)){let r,o=s[1],a=s[2];switch(o){case"rgb":case"rgba":if(r=/^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return n(r[4]),this.setRGB(Math.min(255,parseInt(r[1],10))/255,Math.min(255,parseInt(r[2],10))/255,Math.min(255,parseInt(r[3],10))/255,e);if(r=/^\s*(\d+)\%\s*,\s*(\d+)\%\s*,\s*(\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return n(r[4]),this.setRGB(Math.min(100,parseInt(r[1],10))/100,Math.min(100,parseInt(r[2],10))/100,Math.min(100,parseInt(r[3],10))/100,e);break;case"hsl":case"hsla":if(r=/^\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\%\s*,\s*(\d*\.?\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return n(r[4]),this.setHSL(parseFloat(r[1])/360,parseFloat(r[2])/100,parseFloat(r[3])/100,e);break;default:pt("Color: Unknown color model "+t)}}else if(s=/^\#([A-Fa-f\d]+)$/.exec(t)){let r=s[1],o=r.length;if(o===3)return this.setRGB(parseInt(r.charAt(0),16)/15,parseInt(r.charAt(1),16)/15,parseInt(r.charAt(2),16)/15,e);if(o===6)return this.setHex(parseInt(r,16),e);pt("Color: Invalid hex color "+t)}else if(t&&t.length>0)return this.setColorName(t,e);return this}setColorName(t,e=kt){let n=Nr[t.toLowerCase()];return n!==void 0?this.setHex(n,e):pt("Color: Unknown color "+t),this}clone(){return new this.constructor(this.r,this.g,this.b)}copy(t){return this.r=t.r,this.g=t.g,this.b=t.b,this}copySRGBToLinear(t){return this.r=Qt(t.r),this.g=Qt(t.g),this.b=Qt(t.b),this}copyLinearToSRGB(t){return this.r=Ge(t.r),this.g=Ge(t.g),this.b=Ge(t.b),this}convertSRGBToLinear(){return this.copySRGBToLinear(this),this}convertLinearToSRGB(){return this.copyLinearToSRGB(this),this}getHex(t=kt){return zt.workingToColorSpace(Mt.copy(this),t),Math.round(j(Mt.r*255,0,255))*65536+Math.round(j(Mt.g*255,0,255))*256+Math.round(j(Mt.b*255,0,255))}getHexString(t=kt){return("000000"+this.getHex(t).toString(16)).slice(-6)}getHSL(t,e=zt.workingColorSpace){zt.workingToColorSpace(Mt.copy(this),e);let n=Mt.r,s=Mt.g,r=Mt.b,o=Math.max(n,s,r),a=Math.min(n,s,r),c,l,u=(a+o)/2;if(a===o)c=0,l=0;else{let h=o-a;switch(l=u<=.5?h/(o+a):h/(2-o-a),o){case n:c=(s-r)/h+(s<r?6:0);break;case s:c=(r-n)/h+2;break;case r:c=(n-s)/h+4;break}c/=6}return t.h=c,t.s=l,t.l=u,t}getRGB(t,e=zt.workingColorSpace){return zt.workingToColorSpace(Mt.copy(this),e),t.r=Mt.r,t.g=Mt.g,t.b=Mt.b,t}getStyle(t=kt){zt.workingToColorSpace(Mt.copy(this),t);let e=Mt.r,n=Mt.g,s=Mt.b;return t!==kt?`color(${t} ${e.toFixed(3)} ${n.toFixed(3)} ${s.toFixed(3)})`:`rgb(${Math.round(e*255)},${Math.round(n*255)},${Math.round(s*255)})`}offsetHSL(t,e,n){return this.getHSL(oe),this.setHSL(oe.h+t,oe.s+e,oe.l+n)}add(t){return this.r+=t.r,this.g+=t.g,this.b+=t.b,this}addColors(t,e){return this.r=t.r+e.r,this.g=t.g+e.g,this.b=t.b+e.b,this}addScalar(t){return this.r+=t,this.g+=t,this.b+=t,this}sub(t){return this.r=Math.max(0,this.r-t.r),this.g=Math.max(0,this.g-t.g),this.b=Math.max(0,this.b-t.b),this}multiply(t){return this.r*=t.r,this.g*=t.g,this.b*=t.b,this}multiplyScalar(t){return this.r*=t,this.g*=t,this.b*=t,this}lerp(t,e){return this.r+=(t.r-this.r)*e,this.g+=(t.g-this.g)*e,this.b+=(t.b-this.b)*e,this}lerpColors(t,e,n){return this.r=t.r+(e.r-t.r)*n,this.g=t.g+(e.g-t.g)*n,this.b=t.b+(e.b-t.b)*n,this}lerpHSL(t,e){this.getHSL(oe),t.getHSL(Dn);let n=Ei(oe.h,Dn.h,e),s=Ei(oe.s,Dn.s,e),r=Ei(oe.l,Dn.l,e);return this.setHSL(n,s,r),this}setFromVector3(t){return this.r=t.x,this.g=t.y,this.b=t.z,this}applyMatrix3(t){let e=this.r,n=this.g,s=this.b,r=t.elements;return this.r=r[0]*e+r[3]*n+r[6]*s,this.g=r[1]*e+r[4]*n+r[7]*s,this.b=r[2]*e+r[5]*n+r[8]*s,this}equals(t){return t.r===this.r&&t.g===this.g&&t.b===this.b}fromArray(t,e=0){return this.r=t[e],this.g=t[e+1],this.b=t[e+2],this}toArray(t=[],e=0){return t[e]=this.r,t[e+1]=this.g,t[e+2]=this.b,t}fromBufferAttribute(t,e){return this.r=t.getX(e),this.g=t.getY(e),this.b=t.getZ(e),this}toJSON(){return this.getHex()}*[Symbol.iterator](){yield this.r,yield this.g,yield this.b}},Mt=new xt;xt.NAMES=Nr;var le=class{static{p(this,"Box3")}constructor(t=new V(1/0,1/0,1/0),e=new V(-1/0,-1/0,-1/0)){this.isBox3=!0,this.min=t,this.max=e}set(t,e){return this.min.copy(t),this.max.copy(e),this}setFromArray(t){this.makeEmpty();for(let e=0,n=t.length;e<n;e+=3)this.expandByPoint(qt.fromArray(t,e));return this}setFromBufferAttribute(t){this.makeEmpty();for(let e=0,n=t.count;e<n;e++)this.expandByPoint(qt.fromBufferAttribute(t,e));return this}setFromPoints(t){this.makeEmpty();for(let e=0,n=t.length;e<n;e++)this.expandByPoint(t[e]);return this}setFromCenterAndSize(t,e){let n=qt.copy(e).multiplyScalar(.5);return this.min.copy(t).sub(n),this.max.copy(t).add(n),this}setFromObject(t,e=!1){return this.makeEmpty(),this.expandByObject(t,e)}clone(){return new this.constructor().copy(this)}copy(t){return this.min.copy(t.min),this.max.copy(t.max),this}makeEmpty(){return this.min.x=this.min.y=this.min.z=1/0,this.max.x=this.max.y=this.max.z=-1/0,this}isEmpty(){return this.max.x<this.min.x||this.max.y<this.min.y||this.max.z<this.min.z}getCenter(t){return this.isEmpty()?t.set(0,0,0):t.addVectors(this.min,this.max).multiplyScalar(.5)}getSize(t){return this.isEmpty()?t.set(0,0,0):t.subVectors(this.max,this.min)}expandByPoint(t){return this.min.min(t),this.max.max(t),this}expandByVector(t){return this.min.sub(t),this.max.add(t),this}expandByScalar(t){return this.min.addScalar(-t),this.max.addScalar(t),this}expandByObject(t,e=!1){t.updateWorldMatrix(!1,!1);let n=t.geometry;if(n!==void 0){let r=n.getAttribute("position");if(e===!0&&r!==void 0&&t.isInstancedMesh!==!0)for(let o=0,a=r.count;o<a;o++)t.isMesh===!0?t.getVertexPosition(o,qt):qt.fromBufferAttribute(r,o),qt.applyMatrix4(t.matrixWorld),this.expandByPoint(qt);else t.boundingBox!==void 0?(t.boundingBox===null&&t.computeBoundingBox(),Un.copy(t.boundingBox)):(n.boundingBox===null&&n.computeBoundingBox(),Un.copy(n.boundingBox)),Un.applyMatrix4(t.matrixWorld),this.union(Un)}let s=t.children;for(let r=0,o=s.length;r<o;r++)this.expandByObject(s[r],e);return this}containsPoint(t){return t.x>=this.min.x&&t.x<=this.max.x&&t.y>=this.min.y&&t.y<=this.max.y&&t.z>=this.min.z&&t.z<=this.max.z}containsBox(t){return this.min.x<=t.min.x&&t.max.x<=this.max.x&&this.min.y<=t.min.y&&t.max.y<=this.max.y&&this.min.z<=t.min.z&&t.max.z<=this.max.z}getParameter(t,e){return e.set((t.x-this.min.x)/(this.max.x-this.min.x),(t.y-this.min.y)/(this.max.y-this.min.y),(t.z-this.min.z)/(this.max.z-this.min.z))}intersectsBox(t){return t.max.x>=this.min.x&&t.min.x<=this.max.x&&t.max.y>=this.min.y&&t.min.y<=this.max.y&&t.max.z>=this.min.z&&t.min.z<=this.max.z}intersectsSphere(t){return this.clampPoint(t.center,qt),qt.distanceToSquared(t.center)<=t.radius*t.radius}intersectsPlane(t){let e,n;return t.normal.x>0?(e=t.normal.x*this.min.x,n=t.normal.x*this.max.x):(e=t.normal.x*this.max.x,n=t.normal.x*this.min.x),t.normal.y>0?(e+=t.normal.y*this.min.y,n+=t.normal.y*this.max.y):(e+=t.normal.y*this.max.y,n+=t.normal.y*this.min.y),t.normal.z>0?(e+=t.normal.z*this.min.z,n+=t.normal.z*this.max.z):(e+=t.normal.z*this.max.z,n+=t.normal.z*this.min.z),e<=-t.constant&&n>=-t.constant}intersectsTriangle(t){if(this.isEmpty())return!1;this.getCenter(cn),Fn.subVectors(this.max,cn),Oe.subVectors(t.a,cn),Be.subVectors(t.b,cn),ze.subVectors(t.c,cn),ae.subVectors(Be,Oe),ce.subVectors(ze,Be),_e.subVectors(Oe,ze);let e=[0,-ae.z,ae.y,0,-ce.z,ce.y,0,-_e.z,_e.y,ae.z,0,-ae.x,ce.z,0,-ce.x,_e.z,0,-_e.x,-ae.y,ae.x,0,-ce.y,ce.x,0,-_e.y,_e.x,0];return!Di(e,Oe,Be,ze,Fn)||(e=[1,0,0,0,1,0,0,0,1],!Di(e,Oe,Be,ze,Fn))?!1:(On.crossVectors(ae,ce),e=[On.x,On.y,On.z],Di(e,Oe,Be,ze,Fn))}clampPoint(t,e){return e.copy(t).clamp(this.min,this.max)}distanceToPoint(t){return this.clampPoint(t,qt).distanceTo(t)}getBoundingSphere(t){return this.isEmpty()?t.makeEmpty():(this.getCenter(t.center),t.radius=this.getSize(qt).length()*.5),t}intersect(t){return this.min.max(t.min),this.max.min(t.max),this.isEmpty()&&this.makeEmpty(),this}union(t){return this.min.min(t.min),this.max.max(t.max),this}applyMatrix4(t){return this.isEmpty()?this:(jt[0].set(this.min.x,this.min.y,this.min.z).applyMatrix4(t),jt[1].set(this.min.x,this.min.y,this.max.z).applyMatrix4(t),jt[2].set(this.min.x,this.max.y,this.min.z).applyMatrix4(t),jt[3].set(this.min.x,this.max.y,this.max.z).applyMatrix4(t),jt[4].set(this.max.x,this.min.y,this.min.z).applyMatrix4(t),jt[5].set(this.max.x,this.min.y,this.max.z).applyMatrix4(t),jt[6].set(this.max.x,this.max.y,this.min.z).applyMatrix4(t),jt[7].set(this.max.x,this.max.y,this.max.z).applyMatrix4(t),this.setFromPoints(jt),this)}translate(t){return this.min.add(t),this.max.add(t),this}equals(t){return t.min.equals(this.min)&&t.max.equals(this.max)}toJSON(){return{min:this.min.toArray(),max:this.max.toArray()}}fromJSON(t){return this.min.fromArray(t.min),this.max.fromArray(t.max),this}},jt=[new V,new V,new V,new V,new V,new V,new V,new V],qt=new V,Un=new le,Oe=new V,Be=new V,ze=new V,ae=new V,ce=new V,_e=new V,cn=new V,Fn=new V,On=new V,ye=new V;function Di(i,t,e,n,s){for(let r=0,o=i.length-3;r<=o;r+=3){ye.fromArray(i,r);let a=s.x*Math.abs(ye.x)+s.y*Math.abs(ye.y)+s.z*Math.abs(ye.z),c=t.dot(ye),l=e.dot(ye),u=n.dot(ye);if(Math.max(-Math.max(c,l,u),Math.min(c,l,u))>a)return!1}return!0}p(Di,"satForAxes");var ut=new V,Bn=new mt,Fa=0,Nt=class extends ve{static{p(this,"BufferAttribute")}constructor(t,e,n=!1){if(super(),Array.isArray(t))throw new TypeError("THREE.BufferAttribute: array should be a Typed Array.");this.isBufferAttribute=!0,Object.defineProperty(this,"id",{value:Fa++}),this.name="",this.array=t,this.itemSize=e,this.count=t!==void 0?t.length/e:0,this.normalized=n,this.usage=Qi,this.updateRanges=[],this.gpuType=Ir,this.version=0}onUploadCallback(){}set needsUpdate(t){t===!0&&this.version++}setUsage(t){return this.usage=t,this}addUpdateRange(t,e){this.updateRanges.push({start:t,count:e})}clearUpdateRanges(){this.updateRanges.length=0}copy(t){return this.name=t.name,this.array=new t.array.constructor(t.array),this.itemSize=t.itemSize,this.count=t.count,this.normalized=t.normalized,this.usage=t.usage,this.gpuType=t.gpuType,this}copyAt(t,e,n){t*=this.itemSize,n*=e.itemSize;for(let s=0,r=this.itemSize;s<r;s++)this.array[t+s]=e.array[n+s];return this}copyArray(t){return this.array.set(t),this}applyMatrix3(t){if(this.itemSize===2)for(let e=0,n=this.count;e<n;e++)Bn.fromBufferAttribute(this,e),Bn.applyMatrix3(t),this.setXY(e,Bn.x,Bn.y);else if(this.itemSize===3)for(let e=0,n=this.count;e<n;e++)ut.fromBufferAttribute(this,e),ut.applyMatrix3(t),this.setXYZ(e,ut.x,ut.y,ut.z);return this}applyMatrix4(t){for(let e=0,n=this.count;e<n;e++)ut.fromBufferAttribute(this,e),ut.applyMatrix4(t),this.setXYZ(e,ut.x,ut.y,ut.z);return this}applyNormalMatrix(t){for(let e=0,n=this.count;e<n;e++)ut.fromBufferAttribute(this,e),ut.applyNormalMatrix(t),this.setXYZ(e,ut.x,ut.y,ut.z);return this}transformDirection(t){for(let e=0,n=this.count;e<n;e++)ut.fromBufferAttribute(this,e),ut.transformDirection(t),this.setXYZ(e,ut.x,ut.y,ut.z);return this}set(t,e=0){return this.array.set(t,e),this}getComponent(t,e){let n=this.array[t*this.itemSize+e];return this.normalized&&(n=on(n,this.array)),n}setComponent(t,e,n){return this.normalized&&(n=wt(n,this.array)),this.array[t*this.itemSize+e]=n,this}getX(t){let e=this.array[t*this.itemSize];return this.normalized&&(e=on(e,this.array)),e}setX(t,e){return this.normalized&&(e=wt(e,this.array)),this.array[t*this.itemSize]=e,this}getY(t){let e=this.array[t*this.itemSize+1];return this.normalized&&(e=on(e,this.array)),e}setY(t,e){return this.normalized&&(e=wt(e,this.array)),this.array[t*this.itemSize+1]=e,this}getZ(t){let e=this.array[t*this.itemSize+2];return this.normalized&&(e=on(e,this.array)),e}setZ(t,e){return this.normalized&&(e=wt(e,this.array)),this.array[t*this.itemSize+2]=e,this}getW(t){let e=this.array[t*this.itemSize+3];return this.normalized&&(e=on(e,this.array)),e}setW(t,e){return this.normalized&&(e=wt(e,this.array)),this.array[t*this.itemSize+3]=e,this}setXY(t,e,n){return t*=this.itemSize,this.normalized&&(e=wt(e,this.array),n=wt(n,this.array)),this.array[t+0]=e,this.array[t+1]=n,this}setXYZ(t,e,n,s){return t*=this.itemSize,this.normalized&&(e=wt(e,this.array),n=wt(n,this.array),s=wt(s,this.array)),this.array[t+0]=e,this.array[t+1]=n,this.array[t+2]=s,this}setXYZW(t,e,n,s,r){return t*=this.itemSize,this.normalized&&(e=wt(e,this.array),n=wt(n,this.array),s=wt(s,this.array),r=wt(r,this.array)),this.array[t+0]=e,this.array[t+1]=n,this.array[t+2]=s,this.array[t+3]=r,this}onUpload(t){return this.onUploadCallback=t,this}clone(){return new this.constructor(this.array,this.itemSize).copy(this)}toJSON(){let t={itemSize:this.itemSize,type:this.array.constructor.name,array:Array.from(this.array),normalized:this.normalized};return this.name!==""&&(t.name=this.name),this.usage!==Qi&&(t.usage=this.usage),t}dispose(){this.dispatchEvent({type:"dispose"})}};var Zn=class extends Nt{static{p(this,"Uint16BufferAttribute")}constructor(t,e,n){super(new Uint16Array(t),e,n)}};var Jn=class extends Nt{static{p(this,"Uint32BufferAttribute")}constructor(t,e,n){super(new Uint32Array(t),e,n)}};var ue=class extends Nt{static{p(this,"Float32BufferAttribute")}constructor(t,e,n){super(new Float32Array(t),e,n)}},Oa=new le,ln=new V,Ui=new V,Kn=class{static{p(this,"Sphere")}constructor(t=new V,e=-1){this.isSphere=!0,this.center=t,this.radius=e}set(t,e){return this.center.copy(t),this.radius=e,this}setFromPoints(t,e){let n=this.center;e!==void 0?n.copy(e):Oa.setFromPoints(t).getCenter(n);let s=0;for(let r=0,o=t.length;r<o;r++)s=Math.max(s,n.distanceToSquared(t[r]));return this.radius=Math.sqrt(s),this}copy(t){return this.center.copy(t.center),this.radius=t.radius,this}isEmpty(){return this.radius<0}makeEmpty(){return this.center.set(0,0,0),this.radius=-1,this}containsPoint(t){return t.distanceToSquared(this.center)<=this.radius*this.radius}distanceToPoint(t){return t.distanceTo(this.center)-this.radius}intersectsSphere(t){let e=this.radius+t.radius;return t.center.distanceToSquared(this.center)<=e*e}intersectsBox(t){return t.intersectsSphere(this)}intersectsPlane(t){return Math.abs(t.distanceToPoint(this.center))<=this.radius}clampPoint(t,e){let n=this.center.distanceToSquared(t);return e.copy(t),n>this.radius*this.radius&&(e.sub(this.center).normalize(),e.multiplyScalar(this.radius).add(this.center)),e}getBoundingBox(t){return this.isEmpty()?(t.makeEmpty(),t):(t.set(this.center,this.center),t.expandByScalar(this.radius),t)}applyMatrix4(t){return this.center.applyMatrix4(t),this.radius=this.radius*t.getMaxScaleOnAxis(),this}translate(t){return this.center.add(t),this}expandByPoint(t){if(this.isEmpty())return this.center.copy(t),this.radius=0,this;ln.subVectors(t,this.center);let e=ln.lengthSq();if(e>this.radius*this.radius){let n=Math.sqrt(e),s=(n-this.radius)*.5;this.center.addScaledVector(ln,s/n),this.radius+=s}return this}union(t){return t.isEmpty()?this:this.isEmpty()?(this.copy(t),this):(this.center.equals(t.center)===!0?this.radius=Math.max(this.radius,t.radius):(Ui.subVectors(t.center,this.center).setLength(t.radius),this.expandByPoint(ln.copy(t.center).add(Ui)),this.expandByPoint(ln.copy(t.center).sub(Ui))),this)}equals(t){return t.center.equals(this.center)&&t.radius===this.radius}clone(){return new this.constructor().copy(this)}toJSON(){return{radius:this.radius,center:this.center.toArray()}}fromJSON(t){return this.radius=t.radius,this.center.fromArray(t.center),this}},Ba=0,Bt=new gt,Fi=new Me,ke=new V,Lt=new le,un=new le,dt=new V,We=class i extends ve{static{p(this,"BufferGeometry")}constructor(){super(),this.isBufferGeometry=!0,Object.defineProperty(this,"id",{value:Ba++}),this.uuid=ci(),this.name="",this.type="BufferGeometry",this.index=null,this.indirect=null,this.indirectOffset=0,this.attributes={},this.morphAttributes={},this.morphTargetsRelative=!1,this.groups=[],this.boundingBox=null,this.boundingSphere=null,this.drawRange={start:0,count:1/0},this.userData={},this._transformed=!1}getIndex(){return this.index}setIndex(t){return Array.isArray(t)?this.index=new(ba(t)?Jn:Zn)(t,1):this.index=t,this}setIndirect(t,e=0){return this.indirect=t,this.indirectOffset=e,this}getIndirect(){return this.indirect}getAttribute(t){return this.attributes[t]}setAttribute(t,e){return this.attributes[t]=e,this}deleteAttribute(t){return delete this.attributes[t],this}hasAttribute(t){return this.attributes[t]!==void 0}addGroup(t,e,n=0){this.groups.push({start:t,count:e,materialIndex:n})}clearGroups(){this.groups=[]}setDrawRange(t,e){this.drawRange.start=t,this.drawRange.count=e}applyMatrix4(t){let e=this.attributes.position;e!==void 0&&(e.applyMatrix4(t),e.needsUpdate=!0);let n=this.attributes.normal;if(n!==void 0){let r=new Y().getNormalMatrix(t);n.applyNormalMatrix(r),n.needsUpdate=!0}let s=this.attributes.tangent;return s!==void 0&&(s.transformDirection(t),s.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this._transformed=!0,this}applyQuaternion(t){return Bt.makeRotationFromQuaternion(t),this.applyMatrix4(Bt),this}rotateX(t){return Bt.makeRotationX(t),this.applyMatrix4(Bt),this}rotateY(t){return Bt.makeRotationY(t),this.applyMatrix4(Bt),this}rotateZ(t){return Bt.makeRotationZ(t),this.applyMatrix4(Bt),this}translate(t,e,n){return Bt.makeTranslation(t,e,n),this.applyMatrix4(Bt),this}scale(t,e,n){return Bt.makeScale(t,e,n),this.applyMatrix4(Bt),this}lookAt(t){return Fi.lookAt(t),Fi.updateMatrix(),this.applyMatrix4(Fi.matrix),this}center(){return this.computeBoundingBox(),this.boundingBox.getCenter(ke).negate(),this.translate(ke.x,ke.y,ke.z),this}setFromPoints(t){let e=this.getAttribute("position");if(e===void 0){let n=[];for(let s=0,r=t.length;s<r;s++){let o=t[s];n.push(o.x,o.y,o.z||0)}this.setAttribute("position",new ue(n,3))}else{let n=Math.min(t.length,e.count);for(let s=0;s<n;s++){let r=t[s];e.setXYZ(s,r.x,r.y,r.z||0)}t.length>e.count&&pt("BufferGeometry: Buffer size too small for points data. Use .dispose() and create a new geometry."),e.needsUpdate=!0}return this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new le);let t=this.attributes.position,e=this.morphAttributes.position;if(t&&t.isGLBufferAttribute){ot("BufferGeometry.computeBoundingBox(): GLBufferAttribute requires a manual bounding box.",this),this.boundingBox.set(new V(-1/0,-1/0,-1/0),new V(1/0,1/0,1/0));return}if(t!==void 0){if(this.boundingBox.setFromBufferAttribute(t),e)for(let n=0,s=e.length;n<s;n++){let r=e[n];Lt.setFromBufferAttribute(r),this.morphTargetsRelative?(dt.addVectors(this.boundingBox.min,Lt.min),this.boundingBox.expandByPoint(dt),dt.addVectors(this.boundingBox.max,Lt.max),this.boundingBox.expandByPoint(dt)):(this.boundingBox.expandByPoint(Lt.min),this.boundingBox.expandByPoint(Lt.max))}}else this.boundingBox.makeEmpty();(isNaN(this.boundingBox.min.x)||isNaN(this.boundingBox.min.y)||isNaN(this.boundingBox.min.z))&&ot('BufferGeometry.computeBoundingBox(): Computed min/max have NaN values. The "position" attribute is likely to have NaN values.',this)}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new Kn);let t=this.attributes.position,e=this.morphAttributes.position;if(t&&t.isGLBufferAttribute){ot("BufferGeometry.computeBoundingSphere(): GLBufferAttribute requires a manual bounding sphere.",this),this.boundingSphere.set(new V,1/0);return}if(t){let n=this.boundingSphere.center;if(Lt.setFromBufferAttribute(t),e)for(let r=0,o=e.length;r<o;r++){let a=e[r];un.setFromBufferAttribute(a),this.morphTargetsRelative?(dt.addVectors(Lt.min,un.min),Lt.expandByPoint(dt),dt.addVectors(Lt.max,un.max),Lt.expandByPoint(dt)):(Lt.expandByPoint(un.min),Lt.expandByPoint(un.max))}Lt.getCenter(n);let s=0;for(let r=0,o=t.count;r<o;r++)dt.fromBufferAttribute(t,r),s=Math.max(s,n.distanceToSquared(dt));if(e)for(let r=0,o=e.length;r<o;r++){let a=e[r],c=this.morphTargetsRelative;for(let l=0,u=a.count;l<u;l++)dt.fromBufferAttribute(a,l),c&&(ke.fromBufferAttribute(t,l),dt.add(ke)),s=Math.max(s,n.distanceToSquared(dt))}this.boundingSphere.radius=Math.sqrt(s),isNaN(this.boundingSphere.radius)&&ot('BufferGeometry.computeBoundingSphere(): Computed radius is NaN. The "position" attribute is likely to have NaN values.',this)}}computeTangents(){let t=this.index,e=this.attributes;if(t===null||e.position===void 0||e.normal===void 0||e.uv===void 0){ot("BufferGeometry: .computeTangents() failed. Missing required attributes (index, position, normal or uv)");return}let n=e.position,s=e.normal,r=e.uv,o=this.getAttribute("tangent");(o===void 0||o.count!==n.count)&&(o=new Nt(new Float32Array(4*n.count),4),this.setAttribute("tangent",o));let a=[],c=[];for(let w=0;w<n.count;w++)a[w]=new V,c[w]=new V;let l=new V,u=new V,h=new V,f=new mt,d=new mt,m=new mt,g=new V,_=new V;function x(w,I,E){l.fromBufferAttribute(n,w),u.fromBufferAttribute(n,I),h.fromBufferAttribute(n,E),f.fromBufferAttribute(r,w),d.fromBufferAttribute(r,I),m.fromBufferAttribute(r,E),u.sub(l),h.sub(l),d.sub(f),m.sub(f);let L=1/(d.x*m.y-m.x*d.y);isFinite(L)&&(g.copy(u).multiplyScalar(m.y).addScaledVector(h,-d.y).multiplyScalar(L),_.copy(h).multiplyScalar(d.x).addScaledVector(u,-m.x).multiplyScalar(L),a[w].add(g),a[I].add(g),a[E].add(g),c[w].add(_),c[I].add(_),c[E].add(_))}p(x,"handleTriangle");let y=this.groups;y.length===0&&(y=[{start:0,count:t.count}]);for(let w=0,I=y.length;w<I;++w){let E=y[w],L=E.start,D=E.count;for(let R=L,C=L+D;R<C;R+=3)x(t.getX(R+0),t.getX(R+1),t.getX(R+2))}let v=new V,b=new V,S=new V,A=new V;function M(w){S.fromBufferAttribute(s,w),A.copy(S);let I=a[w];v.copy(I),v.sub(S.multiplyScalar(S.dot(I))).normalize(),b.crossVectors(A,I);let L=b.dot(c[w])<0?-1:1;o.setXYZW(w,v.x,v.y,v.z,L)}p(M,"handleVertex");for(let w=0,I=y.length;w<I;++w){let E=y[w],L=E.start,D=E.count;for(let R=L,C=L+D;R<C;R+=3)M(t.getX(R+0)),M(t.getX(R+1)),M(t.getX(R+2))}this._transformed=!0}computeVertexNormals(){let t=this.index,e=this.getAttribute("position");if(e!==void 0){let n=this.getAttribute("normal");if(n===void 0||n.count!==e.count)n=new Nt(new Float32Array(e.count*3),3),this.setAttribute("normal",n);else for(let f=0,d=n.count;f<d;f++)n.setXYZ(f,0,0,0);let s=new V,r=new V,o=new V,a=new V,c=new V,l=new V,u=new V,h=new V;if(t)for(let f=0,d=t.count;f<d;f+=3){let m=t.getX(f+0),g=t.getX(f+1),_=t.getX(f+2);s.fromBufferAttribute(e,m),r.fromBufferAttribute(e,g),o.fromBufferAttribute(e,_),u.subVectors(o,r),h.subVectors(s,r),u.cross(h),a.fromBufferAttribute(n,m),c.fromBufferAttribute(n,g),l.fromBufferAttribute(n,_),a.add(u),c.add(u),l.add(u),n.setXYZ(m,a.x,a.y,a.z),n.setXYZ(g,c.x,c.y,c.z),n.setXYZ(_,l.x,l.y,l.z)}else for(let f=0,d=e.count;f<d;f+=3)s.fromBufferAttribute(e,f+0),r.fromBufferAttribute(e,f+1),o.fromBufferAttribute(e,f+2),u.subVectors(o,r),h.subVectors(s,r),u.cross(h),n.setXYZ(f+0,u.x,u.y,u.z),n.setXYZ(f+1,u.x,u.y,u.z),n.setXYZ(f+2,u.x,u.y,u.z);this.normalizeNormals(),n.needsUpdate=!0}}normalizeNormals(){let t=this.attributes.normal;for(let e=0,n=t.count;e<n;e++)dt.fromBufferAttribute(t,e),dt.normalize(),t.setXYZ(e,dt.x,dt.y,dt.z)}toNonIndexed(){function t(a,c){let l=a.array,u=a.itemSize,h=a.normalized,f=new l.constructor(c.length*u),d=0,m=0;for(let g=0,_=c.length;g<_;g++){a.isInterleavedBufferAttribute?d=c[g]*a.data.stride+a.offset:d=c[g]*u;for(let x=0;x<u;x++)f[m++]=l[d++]}return new Nt(f,u,h)}if(p(t,"convertBufferAttribute"),this.index===null)return pt("BufferGeometry.toNonIndexed(): BufferGeometry is already non-indexed."),this;let e=new i,n=this.index.array,s=this.attributes;for(let a in s){let c=s[a],l=t(c,n);e.setAttribute(a,l)}let r=this.morphAttributes;for(let a in r){let c=[],l=r[a];for(let u=0,h=l.length;u<h;u++){let f=l[u],d=t(f,n);c.push(d)}e.morphAttributes[a]=c}e.morphTargetsRelative=this.morphTargetsRelative;let o=this.groups;for(let a=0,c=o.length;a<c;a++){let l=o[a];e.addGroup(l.start,l.count,l.materialIndex)}return e}toJSON(){let t={metadata:{version:4.7,type:"BufferGeometry",generator:"BufferGeometry.toJSON"}};if(t.uuid=this.uuid,t.type=this.parameters!==void 0&&this._transformed===!0?"BufferGeometry":this.type,this.name!==""&&(t.name=this.name),Object.keys(this.userData).length>0&&(t.userData=this.userData),this.parameters!==void 0&&this._transformed!==!0){let c=this.parameters;for(let l in c)c[l]!==void 0&&(t[l]=c[l]);return t}t.data={attributes:{}};let e=this.index;e!==null&&(t.data.index={type:e.array.constructor.name,array:Array.prototype.slice.call(e.array)});let n=this.attributes;for(let c in n){let l=n[c];t.data.attributes[c]=l.toJSON(t.data)}let s={},r=!1;for(let c in this.morphAttributes){let l=this.morphAttributes[c],u=[];for(let h=0,f=l.length;h<f;h++){let d=l[h];u.push(d.toJSON(t.data))}u.length>0&&(s[c]=u,r=!0)}r&&(t.data.morphAttributes=s,t.data.morphTargetsRelative=this.morphTargetsRelative);let o=this.groups;o.length>0&&(t.data.groups=JSON.parse(JSON.stringify(o)));let a=this.boundingSphere;return a!==null&&(t.data.boundingSphere=a.toJSON()),t}clone(){return new this.constructor().copy(this)}copy(t){this.index=null,this.attributes={},this.morphAttributes={},this.groups=[],this.boundingBox=null,this.boundingSphere=null;let e={};this.name=t.name;let n=t.index;n!==null&&this.setIndex(n.clone());let s=t.attributes;for(let l in s){let u=s[l];this.setAttribute(l,u.clone(e))}let r=t.morphAttributes;for(let l in r){let u=[],h=r[l];for(let f=0,d=h.length;f<d;f++)u.push(h[f].clone(e));this.morphAttributes[l]=u}this.morphTargetsRelative=t.morphTargetsRelative;let o=t.groups;for(let l=0,u=o.length;l<u;l++){let h=o[l];this.addGroup(h.start,h.count,h.materialIndex)}let a=t.boundingBox;a!==null&&(this.boundingBox=a.clone());let c=t.boundingSphere;return c!==null&&(this.boundingSphere=c.clone()),this.drawRange.start=t.drawRange.start,this.drawRange.count=t.drawRange.count,this.userData=t.userData,this._transformed=t._transformed,this}dispose(){this.dispatchEvent({type:"dispose"})}};function za(i,t,e=2){let n=t&&t.length,s=n?t[0]*e:i.length,r=Dr(i,0,s,e,!0),o=[];if(!r||r.next===r.prev)return o;let a,c,l;if(n&&(r=Wa(i,t,r,e)),i.length>80*e){a=i[0],c=i[1];let u=a,h=c;for(let f=e;f<s;f+=e){let d=i[f],m=i[f+1];d<a&&(a=d),m<c&&(c=m),d>u&&(u=d),m>h&&(h=m)}l=Math.max(u-a,h-c),l=l!==0?32767/l:0}return gn(r,o,e,a,c,l,0),o}p(za,"earcut");function Dr(i,t,e,n,s){let r;if(s===ec(i,t,e,n)>0)for(let o=t;o<e;o+=n)r=gr(o/n|0,i[o],i[o+1],r);else for(let o=e-n;o>=t;o-=n)r=gr(o/n|0,i[o],i[o+1],r);return r&&Xe(r,r.next)&&(_n(r),r=r.next),r}p(Dr,"linkedList");function be(i,t){if(!i)return i;t||(t=i);let e=i,n;do if(n=!1,!e.steiner&&(Xe(e,e.next)||at(e.prev,e,e.next)===0)){if(_n(e),e=t=e.prev,e===e.next)break;n=!0}else e=e.next;while(n||e!==t);return t}p(be,"filterPoints");function gn(i,t,e,n,s,r,o){if(!i)return;!o&&r&&Za(i,n,s,r);let a=i;for(;i.prev!==i.next;){let c=i.prev,l=i.next;if(r?Va(i,n,s,r):ka(i)){t.push(c.i,i.i,l.i),_n(i),i=l.next,a=l.next;continue}if(i=l,i===a){o?o===1?(i=Ga(be(i),t),gn(i,t,e,n,s,r,2)):o===2&&Ha(i,t,e,n,s,r):gn(be(i),t,e,n,s,r,1);break}}}p(gn,"earcutLinked");function ka(i){let t=i.prev,e=i,n=i.next;if(at(t,e,n)>=0)return!1;let s=t.x,r=e.x,o=n.x,a=t.y,c=e.y,l=n.y,u=Math.min(s,r,o),h=Math.min(a,c,l),f=Math.max(s,r,o),d=Math.max(a,c,l),m=n.next;for(;m!==t;){if(m.x>=u&&m.x<=f&&m.y>=h&&m.y<=d&&dn(s,a,r,c,o,l,m.x,m.y)&&at(m.prev,m,m.next)>=0)return!1;m=m.next}return!0}p(ka,"isEar");function Va(i,t,e,n){let s=i.prev,r=i,o=i.next;if(at(s,r,o)>=0)return!1;let a=s.x,c=r.x,l=o.x,u=s.y,h=r.y,f=o.y,d=Math.min(a,c,l),m=Math.min(u,h,f),g=Math.max(a,c,l),_=Math.max(u,h,f),x=is(d,m,t,e,n),y=is(g,_,t,e,n),v=i.prevZ,b=i.nextZ;for(;v&&v.z>=x&&b&&b.z<=y;){if(v.x>=d&&v.x<=g&&v.y>=m&&v.y<=_&&v!==s&&v!==o&&dn(a,u,c,h,l,f,v.x,v.y)&&at(v.prev,v,v.next)>=0||(v=v.prevZ,b.x>=d&&b.x<=g&&b.y>=m&&b.y<=_&&b!==s&&b!==o&&dn(a,u,c,h,l,f,b.x,b.y)&&at(b.prev,b,b.next)>=0))return!1;b=b.nextZ}for(;v&&v.z>=x;){if(v.x>=d&&v.x<=g&&v.y>=m&&v.y<=_&&v!==s&&v!==o&&dn(a,u,c,h,l,f,v.x,v.y)&&at(v.prev,v,v.next)>=0)return!1;v=v.prevZ}for(;b&&b.z<=y;){if(b.x>=d&&b.x<=g&&b.y>=m&&b.y<=_&&b!==s&&b!==o&&dn(a,u,c,h,l,f,b.x,b.y)&&at(b.prev,b,b.next)>=0)return!1;b=b.nextZ}return!0}p(Va,"isEarHashed");function Ga(i,t){let e=i;do{let n=e.prev,s=e.next.next;!Xe(n,s)&&Fr(n,e,e.next,s)&&xn(n,s)&&xn(s,n)&&(t.push(n.i,e.i,s.i),_n(e),_n(e.next),e=i=s),e=e.next}while(e!==i);return be(e)}p(Ga,"cureLocalIntersections");function Ha(i,t,e,n,s,r){let o=i;do{let a=o.next.next;for(;a!==o.prev;){if(o.i!==a.i&&ja(o,a)){let c=Or(o,a);o=be(o,o.next),c=be(c,c.next),gn(o,t,e,n,s,r,0),gn(c,t,e,n,s,r,0);return}a=a.next}o=o.next}while(o!==i)}p(Ha,"splitEarcut");function Wa(i,t,e,n){let s=[];for(let r=0,o=t.length;r<o;r++){let a=t[r]*n,c=r<o-1?t[r+1]*n:i.length,l=Dr(i,a,c,n,!1);l===l.next&&(l.steiner=!0),s.push(Ka(l))}s.sort(Xa);for(let r=0;r<s.length;r++)e=qa(s[r],e);return e}p(Wa,"eliminateHoles");function Xa(i,t){let e=i.x-t.x;if(e===0&&(e=i.y-t.y,e===0)){let n=(i.next.y-i.y)/(i.next.x-i.x),s=(t.next.y-t.y)/(t.next.x-t.x);e=n-s}return e}p(Xa,"compareXYSlope");function qa(i,t){let e=$a(i,t);if(!e)return t;let n=Or(e,i);return be(n,n.next),be(e,e.next)}p(qa,"eliminateHole");function $a(i,t){let e=t,n=i.x,s=i.y,r=-1/0,o;if(Xe(i,e))return e;do{if(Xe(i,e.next))return e.next;if(s<=e.y&&s>=e.next.y&&e.next.y!==e.y){let h=e.x+(s-e.y)*(e.next.x-e.x)/(e.next.y-e.y);if(h<=n&&h>r&&(r=h,o=e.x<e.next.x?e:e.next,h===n))return o}e=e.next}while(e!==t);if(!o)return null;let a=o,c=o.x,l=o.y,u=1/0;e=o;do{if(n>=e.x&&e.x>=c&&n!==e.x&&Ur(s<l?n:r,s,c,l,s<l?r:n,s,e.x,e.y)){let h=Math.abs(s-e.y)/(n-e.x);xn(e,i)&&(h<u||h===u&&(e.x>o.x||e.x===o.x&&Ya(o,e)))&&(o=e,u=h)}e=e.next}while(e!==a);return o}p($a,"findHoleBridge");function Ya(i,t){return at(i.prev,i,t.prev)<0&&at(t.next,i,i.next)<0}p(Ya,"sectorContainsSector");function Za(i,t,e,n){let s=i;do s.z===0&&(s.z=is(s.x,s.y,t,e,n)),s.prevZ=s.prev,s.nextZ=s.next,s=s.next;while(s!==i);s.prevZ.nextZ=null,s.prevZ=null,Ja(s)}p(Za,"indexCurve");function Ja(i){let t,e=1;do{let n=i,s;i=null;let r=null;for(t=0;n;){t++;let o=n,a=0;for(let l=0;l<e&&(a++,o=o.nextZ,!!o);l++);let c=e;for(;a>0||c>0&&o;)a!==0&&(c===0||!o||n.z<=o.z)?(s=n,n=n.nextZ,a--):(s=o,o=o.nextZ,c--),r?r.nextZ=s:i=s,s.prevZ=r,r=s;n=o}r.nextZ=null,e*=2}while(t>1);return i}p(Ja,"sortLinked");function is(i,t,e,n,s){return i=(i-e)*s|0,t=(t-n)*s|0,i=(i|i<<8)&16711935,i=(i|i<<4)&252645135,i=(i|i<<2)&858993459,i=(i|i<<1)&1431655765,t=(t|t<<8)&16711935,t=(t|t<<4)&252645135,t=(t|t<<2)&858993459,t=(t|t<<1)&1431655765,i|t<<1}p(is,"zOrder");function Ka(i){let t=i,e=i;do(t.x<e.x||t.x===e.x&&t.y<e.y)&&(e=t),t=t.next;while(t!==i);return e}p(Ka,"getLeftmost");function Ur(i,t,e,n,s,r,o,a){return(s-o)*(t-a)>=(i-o)*(r-a)&&(i-o)*(n-a)>=(e-o)*(t-a)&&(e-o)*(r-a)>=(s-o)*(n-a)}p(Ur,"pointInTriangle");function dn(i,t,e,n,s,r,o,a){return!(i===o&&t===a)&&Ur(i,t,e,n,s,r,o,a)}p(dn,"pointInTriangleExceptFirst");function ja(i,t){return i.next.i!==t.i&&i.prev.i!==t.i&&!Qa(i,t)&&(xn(i,t)&&xn(t,i)&&tc(i,t)&&(at(i.prev,i,t.prev)||at(i,t.prev,t))||Xe(i,t)&&at(i.prev,i,i.next)>0&&at(t.prev,t,t.next)>0)}p(ja,"isValidDiagonal");function at(i,t,e){return(t.y-i.y)*(e.x-t.x)-(t.x-i.x)*(e.y-t.y)}p(at,"area");function Xe(i,t){return i.x===t.x&&i.y===t.y}p(Xe,"equals");function Fr(i,t,e,n){let s=kn(at(i,t,e)),r=kn(at(i,t,n)),o=kn(at(e,n,i)),a=kn(at(e,n,t));return!!(s!==r&&o!==a||s===0&&zn(i,e,t)||r===0&&zn(i,n,t)||o===0&&zn(e,i,n)||a===0&&zn(e,t,n))}p(Fr,"intersects");function zn(i,t,e){return t.x<=Math.max(i.x,e.x)&&t.x>=Math.min(i.x,e.x)&&t.y<=Math.max(i.y,e.y)&&t.y>=Math.min(i.y,e.y)}p(zn,"onSegment");function kn(i){return i>0?1:i<0?-1:0}p(kn,"sign");function Qa(i,t){let e=i;do{if(e.i!==i.i&&e.next.i!==i.i&&e.i!==t.i&&e.next.i!==t.i&&Fr(e,e.next,i,t))return!0;e=e.next}while(e!==i);return!1}p(Qa,"intersectsPolygon");function xn(i,t){return at(i.prev,i,i.next)<0?at(i,t,i.next)>=0&&at(i,i.prev,t)>=0:at(i,t,i.prev)<0||at(i,i.next,t)<0}p(xn,"locallyInside");function tc(i,t){let e=i,n=!1,s=(i.x+t.x)/2,r=(i.y+t.y)/2;do e.y>r!=e.next.y>r&&e.next.y!==e.y&&s<(e.next.x-e.x)*(r-e.y)/(e.next.y-e.y)+e.x&&(n=!n),e=e.next;while(e!==i);return n}p(tc,"middleInside");function Or(i,t){let e=ss(i.i,i.x,i.y),n=ss(t.i,t.x,t.y),s=i.next,r=t.prev;return i.next=t,t.prev=i,e.next=s,s.prev=e,n.next=e,e.prev=n,r.next=n,n.prev=r,n}p(Or,"splitPolygon");function gr(i,t,e,n){let s=ss(i,t,e);return n?(s.next=n.next,s.prev=n,n.next.prev=s,n.next=s):(s.prev=s,s.next=s),s}p(gr,"insertNode");function _n(i){i.next.prev=i.prev,i.prev.next=i.next,i.prevZ&&(i.prevZ.nextZ=i.nextZ),i.nextZ&&(i.nextZ.prevZ=i.prevZ)}p(_n,"removeNode");function ss(i,t,e){return{i,x:t,y:e,prev:null,next:null,z:0,prevZ:null,nextZ:null,steiner:!1}}p(ss,"createNode");function ec(i,t,e,n){let s=0;for(let r=t,o=e-n;r<e;r+=n)s+=(i[o]-i[r])*(i[r+1]+i[o+1]),o=r;return s}p(ec,"signedArea");var rs=class{static{p(this,"Earcut")}static triangulate(t,e,n=2){return za(t,e,n)}},yn=class i{static{p(this,"ShapeUtils")}static area(t){let e=t.length,n=0;for(let s=e-1,r=0;r<e;s=r++)n+=t[s].x*t[r].y-t[r].x*t[s].y;return n*.5}static isClockWise(t){return i.area(t)<0}static triangulateShape(t,e){let n=[],s=[],r=[];xr(t),_r(n,t);let o=t.length;e.forEach(xr);for(let c=0;c<e.length;c++)s.push(o),o+=e[c].length,_r(n,e[c]);let a=rs.triangulate(n,s);for(let c=0;c<a.length;c+=3)r.push(a.slice(c,c+3));return r}};function xr(i){let t=i.length;t>2&&i[t-1].equals(i[0])&&i.pop()}p(xr,"removeDupEndPts");function _r(i,t){for(let e=0;e<t.length;e++)i.push(t[e].x),i.push(t[e].y)}p(_r,"addContour");function Br(i){let t={};for(let e in i){t[e]={};for(let n in i[e]){let s=i[e][n];if(yr(s))s.isRenderTargetTexture?(pt("UniformsUtils: Textures of render targets cannot be cloned via cloneUniforms() or mergeUniforms()."),t[e][n]=null):t[e][n]=s.clone();else if(Array.isArray(s))if(yr(s[0])){let r=[];for(let o=0,a=s.length;o<a;o++)r[o]=s[o].clone();t[e][n]=r}else t[e][n]=s.slice();else t[e][n]=s}}return t}p(Br,"cloneUniforms");function bt(i){let t={};for(let e=0;e<i.length;e++){let n=Br(i[e]);for(let s in n)t[s]=n[s]}return t}p(bt,"mergeUniforms");function yr(i){return i&&(i.isColor||i.isMatrix3||i.isMatrix4||i.isVector2||i.isVector3||i.isVector4||i.isTexture||i.isQuaternion)}p(yr,"isThreeObject");function Vn(i,t){return!i||i.constructor===t?i:typeof t.BYTES_PER_ELEMENT=="number"?new t(i):Array.prototype.slice.call(i)}p(Vn,"convertArray");var he=class{static{p(this,"Interpolant")}constructor(t,e,n,s){this.parameterPositions=t,this._cachedIndex=0,this.resultBuffer=s!==void 0?s:new e.constructor(n),this.sampleValues=e,this.valueSize=n,this.settings=null,this.DefaultSettings_={}}evaluate(t){let e=this.parameterPositions,n=this._cachedIndex,s=e[n],r=e[n-1];n:{t:{let o;e:{i:if(!(t<s)){for(let a=n+2;;){if(s===void 0){if(t<r)break i;return n=e.length,this._cachedIndex=n,this.copySampleValue_(n-1)}if(n===a)break;if(r=s,s=e[++n],t<s)break t}o=e.length;break e}if(!(t>=r)){let a=e[1];t<a&&(n=2,r=a);for(let c=n-2;;){if(r===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(n===c)break;if(s=r,r=e[--n-1],t>=r)break t}o=n,n=0;break e}break n}for(;n<o;){let a=n+o>>>1;t<e[a]?o=a:n=a+1}if(s=e[n],r=e[n-1],r===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(s===void 0)return n=e.length,this._cachedIndex=n,this.copySampleValue_(n-1)}this._cachedIndex=n,this.intervalChanged_(n,r,s)}return this.interpolate_(n,r,t,s)}getSettings_(){return this.settings||this.DefaultSettings_}copySampleValue_(t){let e=this.resultBuffer,n=this.sampleValues,s=this.valueSize,r=t*s;for(let o=0;o!==s;++o)e[o]=n[r+o];return e}interpolate_(){throw new Error("THREE.Interpolant: Call to abstract method.")}intervalChanged_(){}},jn=class extends he{static{p(this,"CubicInterpolant")}constructor(t,e,n,s){super(t,e,n,s),this._weightPrev=-0,this._offsetPrev=-0,this._weightNext=-0,this._offsetNext=-0,this.DefaultSettings_={endingStart:Yi,endingEnd:Yi}}intervalChanged_(t,e,n){let s=this.parameterPositions,r=t-2,o=t+1,a=s[r],c=s[o];if(a===void 0)switch(this.getSettings_().endingStart){case Zi:r=t,a=2*e-n;break;case Ji:r=s.length-2,a=e+s[r]-s[r+1];break;default:r=t,a=n}if(c===void 0)switch(this.getSettings_().endingEnd){case Zi:o=t,c=2*n-e;break;case Ji:o=1,c=n+s[1]-s[0];break;default:o=t-1,c=e}let l=(n-e)*.5,u=this.valueSize;this._weightPrev=l/(e-a),this._weightNext=l/(c-n),this._offsetPrev=r*u,this._offsetNext=o*u}interpolate_(t,e,n,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=this._offsetPrev,h=this._offsetNext,f=this._weightPrev,d=this._weightNext,m=(n-e)/(s-e),g=m*m,_=g*m,x=-f*_+2*f*g-f*m,y=(1+f)*_+(-1.5-2*f)*g+(-.5+f)*m+1,v=(-1-d)*_+(1.5+d)*g+.5*m,b=d*_-d*g;for(let S=0;S!==a;++S)r[S]=x*o[u+S]+y*o[l+S]+v*o[c+S]+b*o[h+S];return r}},Qn=class extends he{static{p(this,"LinearInterpolant")}constructor(t,e,n,s){super(t,e,n,s)}interpolate_(t,e,n,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=(n-e)/(s-e),h=1-u;for(let f=0;f!==a;++f)r[f]=o[l+f]*h+o[c+f]*u;return r}},ti=class extends he{static{p(this,"DiscreteInterpolant")}constructor(t,e,n,s){super(t,e,n,s)}interpolate_(t){return this.copySampleValue_(t-1)}},ei=class extends he{static{p(this,"BezierInterpolant")}interpolate_(t,e,n,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=this.inTangents,h=this.outTangents;if(!u||!h){let m=(n-e)/(s-e),g=1-m;for(let _=0;_!==a;++_)r[_]=o[l+_]*g+o[c+_]*m;return r}let f=a*2,d=t-1;for(let m=0;m!==a;++m){let g=o[l+m],_=o[c+m],x=d*f+m*2,y=h[x],v=h[x+1],b=t*f+m*2,S=u[b],A=u[b+1],M=(n-e)/(s-e),w,I,E,L,D;for(let R=0;R<8;R++){w=M*M,I=w*M,E=1-M,L=E*E,D=L*E;let P=D*e+3*L*M*y+3*E*w*S+I*s-n;if(Math.abs(P)<1e-10)break;let T=3*L*(y-e)+6*E*M*(S-y)+3*w*(s-S);if(Math.abs(T)<1e-10)break;M=M-P/T,M=Math.max(0,Math.min(1,M))}r[m]=D*g+3*L*M*v+3*E*w*A+I*_}return r}},Dt=class{static{p(this,"KeyframeTrack")}constructor(t,e,n,s){if(t===void 0)throw new Error("THREE.KeyframeTrack: track name is undefined");if(e===void 0||e.length===0)throw new Error("THREE.KeyframeTrack: no keyframes in track named "+t);this.name=t,this.times=Vn(e,this.TimeBufferType),this.values=Vn(n,this.ValueBufferType),this.setInterpolation(s||this.DefaultInterpolation)}static toJSON(t){let e=t.constructor,n;if(e.toJSON!==this.toJSON)n=e.toJSON(t);else{n={name:t.name,times:Vn(t.times,Array),values:Vn(t.values,Array)};let s=t.getInterpolation();s!==t.DefaultInterpolation&&(n.interpolation=s)}return n.type=t.ValueTypeName,n}InterpolantFactoryMethodDiscrete(t){return new ti(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodLinear(t){return new Qn(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodSmooth(t){return new jn(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodBezier(t){let e=new ei(this.times,this.values,this.getValueSize(),t);return this.settings&&(e.inTangents=this.settings.inTangents,e.outTangents=this.settings.outTangents),e}setInterpolation(t){let e;switch(t){case pn:e=this.InterpolantFactoryMethodDiscrete;break;case Wn:e=this.InterpolantFactoryMethodLinear;break;case Gn:e=this.InterpolantFactoryMethodSmooth;break;case $i:e=this.InterpolantFactoryMethodBezier;break}if(e===void 0){let n="unsupported interpolation for "+this.ValueTypeName+" keyframe track named "+this.name;if(this.createInterpolant===void 0)if(t!==this.DefaultInterpolation)this.setInterpolation(this.DefaultInterpolation);else throw new Error(n);return pt("KeyframeTrack:",n),this}return this.createInterpolant=e,this}getInterpolation(){switch(this.createInterpolant){case this.InterpolantFactoryMethodDiscrete:return pn;case this.InterpolantFactoryMethodLinear:return Wn;case this.InterpolantFactoryMethodSmooth:return Gn;case this.InterpolantFactoryMethodBezier:return $i}}getValueSize(){return this.values.length/this.times.length}shift(t){if(t!==0){let e=this.times;for(let n=0,s=e.length;n!==s;++n)e[n]+=t}return this}scale(t){if(t!==1){let e=this.times;for(let n=0,s=e.length;n!==s;++n)e[n]*=t}return this}trim(t,e){let n=this.times,s=n.length,r=0,o=s-1;for(;r!==s&&n[r]<t;)++r;for(;o!==-1&&n[o]>e;)--o;if(++o,r!==0||o!==s){r>=o&&(o=Math.max(o,1),r=o-1);let a=this.getValueSize();this.times=n.slice(r,o),this.values=this.values.slice(r*a,o*a)}return this}validate(){let t=!0,e=this.getValueSize();e-Math.floor(e)!==0&&(ot("KeyframeTrack: Invalid value size in track.",this),t=!1);let n=this.times,s=this.values,r=n.length;r===0&&(ot("KeyframeTrack: Track is empty.",this),t=!1);let o=null;for(let a=0;a!==r;a++){let c=n[a];if(typeof c=="number"&&isNaN(c)){ot("KeyframeTrack: Time is not a valid number.",this,a,c),t=!1;break}if(o!==null&&o>c){ot("KeyframeTrack: Out of order keys.",this,a,c,o),t=!1;break}o=c}if(s!==void 0&&Sa(s))for(let a=0,c=s.length;a!==c;++a){let l=s[a];if(isNaN(l)){ot("KeyframeTrack: Value is not a valid number.",this,a,l),t=!1;break}}return t}optimize(){let t=this.times.slice(),e=this.values.slice(),n=this.getValueSize(),s=this.getInterpolation()===Gn,r=t.length-1,o=1;for(let a=1;a<r;++a){let c=!1,l=t[a],u=t[a+1];if(l!==u&&(a!==1||l!==t[0]))if(s)c=!0;else{let h=a*n,f=h-n,d=h+n;for(let m=0;m!==n;++m){let g=e[h+m];if(g!==e[f+m]||g!==e[d+m]){c=!0;break}}}if(c){if(a!==o){t[o]=t[a];let h=a*n,f=o*n;for(let d=0;d!==n;++d)e[f+d]=e[h+d]}++o}}if(r>0){t[o]=t[r];for(let a=r*n,c=o*n,l=0;l!==n;++l)e[c+l]=e[a+l];++o}return o!==t.length?(this.times=t.slice(0,o),this.values=e.slice(0,o*n)):(this.times=t,this.values=e),this}clone(){let t=this.times.slice(),e=this.values.slice(),n=this.constructor,s=new n(this.name,t,e);return s.createInterpolant=this.createInterpolant,s}};Dt.prototype.ValueTypeName="";Dt.prototype.TimeBufferType=Float32Array;Dt.prototype.ValueBufferType=Float32Array;Dt.prototype.DefaultInterpolation=Wn;var fe=class extends Dt{static{p(this,"BooleanKeyframeTrack")}constructor(t,e,n){super(t,e,n)}};fe.prototype.ValueTypeName="bool";fe.prototype.ValueBufferType=Array;fe.prototype.DefaultInterpolation=pn;fe.prototype.InterpolantFactoryMethodLinear=void 0;fe.prototype.InterpolantFactoryMethodSmooth=void 0;var ni=class extends Dt{static{p(this,"ColorKeyframeTrack")}constructor(t,e,n,s){super(t,e,n,s)}};ni.prototype.ValueTypeName="color";var ii=class extends Dt{static{p(this,"NumberKeyframeTrack")}constructor(t,e,n,s){super(t,e,n,s)}};ii.prototype.ValueTypeName="number";var si=class extends he{static{p(this,"QuaternionLinearInterpolant")}constructor(t,e,n,s){super(t,e,n,s)}interpolate_(t,e,n,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=(n-e)/(s-e),l=t*a;for(let u=l+a;l!==u;l+=4)$t.slerpFlat(r,0,o,l-a,o,l,c);return r}},vn=class extends Dt{static{p(this,"QuaternionKeyframeTrack")}constructor(t,e,n,s){super(t,e,n,s)}InterpolantFactoryMethodLinear(t){return new si(this.times,this.values,this.getValueSize(),t)}};vn.prototype.ValueTypeName="quaternion";vn.prototype.InterpolantFactoryMethodSmooth=void 0;var de=class extends Dt{static{p(this,"StringKeyframeTrack")}constructor(t,e,n){super(t,e,n)}};de.prototype.ValueTypeName="string";de.prototype.ValueBufferType=Array;de.prototype.DefaultInterpolation=pn;de.prototype.InterpolantFactoryMethodLinear=void 0;de.prototype.InterpolantFactoryMethodSmooth=void 0;var ri=class extends Dt{static{p(this,"VectorKeyframeTrack")}constructor(t,e,n,s){super(t,e,n,s)}};ri.prototype.ValueTypeName="vector";var oi=class{static{p(this,"LoadingManager")}constructor(t,e,n){let s=this,r=!1,o=0,a=0,c,l=[];this.onStart=void 0,this.onLoad=t,this.onProgress=e,this.onError=n,this._abortController=null,this.itemStart=function(u){a++,r===!1&&s.onStart!==void 0&&s.onStart(u,o,a),r=!0},this.itemEnd=function(u){o++,s.onProgress!==void 0&&s.onProgress(u,o,a),o===a&&(r=!1,s.onLoad!==void 0&&s.onLoad())},this.itemError=function(u){s.onError!==void 0&&s.onError(u)},this.resolveURL=function(u){return u=u.normalize("NFC"),c?c(u):u},this.setURLModifier=function(u){return c=u,this},this.addHandler=function(u,h){return l.push(u,h),this},this.removeHandler=function(u){let h=l.indexOf(u);return h!==-1&&l.splice(h,2),this},this.getHandler=function(u){for(let h=0,f=l.length;h<f;h+=2){let d=l[h],m=l[h+1];if(d.global&&(d.lastIndex=0),d.test(u))return m}return null},this.abort=function(){return this.abortController.abort(),this._abortController=null,this}}get abortController(){return this._abortController||(this._abortController=new AbortController),this._abortController}},zr=new oi,ai=class{static{p(this,"Loader")}constructor(t){this.manager=t!==void 0?t:zr,this.crossOrigin="anonymous",this.withCredentials=!1,this.path="",this.resourcePath="",this.requestHeader={},typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}load(){}loadAsync(t,e){let n=this;return new Promise(function(s,r){n.load(t,s,e,r)})}parse(){}setCrossOrigin(t){return this.crossOrigin=t,this}setWithCredentials(t){return this.withCredentials=t,this}setPath(t){return this.path=t,this}setResourcePath(t){return this.resourcePath=t,this}setRequestHeader(t){return this.requestHeader=t,this}abort(){return this}};ai.DEFAULT_MATERIAL_NAME="__DEFAULT";var _s="\\[\\]\\.:\\/",nc=new RegExp("["+_s+"]","g"),ys="[^"+_s+"]",ic="[^"+_s.replace("\\.","")+"]",sc=/((?:WC+[\/:])*)/.source.replace("WC",ys),rc=/(WCOD+)?/.source.replace("WCOD",ic),oc=/(?:\.(WC+)(?:\[(.+)\])?)?/.source.replace("WC",ys),ac=/\.(WC+)(?:\[(.+)\])?/.source.replace("WC",ys),cc=new RegExp("^"+sc+rc+oc+ac+"$"),lc=["material","materials","bones","map"],os=class{static{p(this,"Composite")}constructor(t,e,n){let s=n||it.parseTrackName(e);this._targetGroup=t,this._bindings=t.subscribe_(e,s)}getValue(t,e){this.bind();let n=this._targetGroup.nCachedObjects_,s=this._bindings[n];s!==void 0&&s.getValue(t,e)}setValue(t,e){let n=this._bindings;for(let s=this._targetGroup.nCachedObjects_,r=n.length;s!==r;++s)n[s].setValue(t,e)}bind(){let t=this._bindings;for(let e=this._targetGroup.nCachedObjects_,n=t.length;e!==n;++e)t[e].bind()}unbind(){let t=this._bindings;for(let e=this._targetGroup.nCachedObjects_,n=t.length;e!==n;++e)t[e].unbind()}},it=class i{static{p(this,"PropertyBinding")}constructor(t,e,n){this.path=e,this.parsedPath=n||i.parseTrackName(e),this.node=i.findNode(t,this.parsedPath.nodeName),this.rootNode=t,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}static create(t,e,n){return t&&t.isAnimationObjectGroup?new i.Composite(t,e,n):new i(t,e,n)}static sanitizeNodeName(t){return t.replace(/\s/g,"_").replace(nc,"")}static parseTrackName(t){let e=cc.exec(t);if(e===null)throw new Error("THREE.PropertyBinding: Cannot parse trackName: "+t);let n={nodeName:e[2],objectName:e[3],objectIndex:e[4],propertyName:e[5],propertyIndex:e[6]},s=n.nodeName&&n.nodeName.lastIndexOf(".");if(s!==void 0&&s!==-1){let r=n.nodeName.substring(s+1);lc.indexOf(r)!==-1&&(n.nodeName=n.nodeName.substring(0,s),n.objectName=r)}if(n.propertyName===null||n.propertyName.length===0)throw new Error("THREE.PropertyBinding: can not parse propertyName from trackName: "+t);return n}static findNode(t,e){if(e===void 0||e===""||e==="."||e===-1||e===t.name||e===t.uuid)return t;if(t.skeleton){let n=t.skeleton.getBoneByName(e);if(n!==void 0)return n}if(t.children){let n=p(function(r){for(let o=0;o<r.length;o++){let a=r[o];if(a.name===e||a.uuid===e)return a;let c=n(a.children);if(c)return c}return null},"searchNodeSubtree"),s=n(t.children);if(s)return s}return null}_getValue_unavailable(){}_setValue_unavailable(){}_getValue_direct(t,e){t[e]=this.targetObject[this.propertyName]}_getValue_array(t,e){let n=this.resolvedProperty;for(let s=0,r=n.length;s!==r;++s)t[e++]=n[s]}_getValue_arrayElement(t,e){t[e]=this.resolvedProperty[this.propertyIndex]}_getValue_toArray(t,e){this.resolvedProperty.toArray(t,e)}_setValue_direct(t,e){this.targetObject[this.propertyName]=t[e]}_setValue_direct_setNeedsUpdate(t,e){this.targetObject[this.propertyName]=t[e],this.targetObject.needsUpdate=!0}_setValue_direct_setMatrixWorldNeedsUpdate(t,e){this.targetObject[this.propertyName]=t[e],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_array(t,e){let n=this.resolvedProperty;for(let s=0,r=n.length;s!==r;++s)n[s]=t[e++]}_setValue_array_setNeedsUpdate(t,e){let n=this.resolvedProperty;for(let s=0,r=n.length;s!==r;++s)n[s]=t[e++];this.targetObject.needsUpdate=!0}_setValue_array_setMatrixWorldNeedsUpdate(t,e){let n=this.resolvedProperty;for(let s=0,r=n.length;s!==r;++s)n[s]=t[e++];this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_arrayElement(t,e){this.resolvedProperty[this.propertyIndex]=t[e]}_setValue_arrayElement_setNeedsUpdate(t,e){this.resolvedProperty[this.propertyIndex]=t[e],this.targetObject.needsUpdate=!0}_setValue_arrayElement_setMatrixWorldNeedsUpdate(t,e){this.resolvedProperty[this.propertyIndex]=t[e],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_fromArray(t,e){this.resolvedProperty.fromArray(t,e)}_setValue_fromArray_setNeedsUpdate(t,e){this.resolvedProperty.fromArray(t,e),this.targetObject.needsUpdate=!0}_setValue_fromArray_setMatrixWorldNeedsUpdate(t,e){this.resolvedProperty.fromArray(t,e),this.targetObject.matrixWorldNeedsUpdate=!0}_getValue_unbound(t,e){this.bind(),this.getValue(t,e)}_setValue_unbound(t,e){this.bind(),this.setValue(t,e)}bind(){let t=this.node,e=this.parsedPath,n=e.objectName,s=e.propertyName,r=e.propertyIndex;if(t||(t=i.findNode(this.rootNode,e.nodeName),this.node=t),this.getValue=this._getValue_unavailable,this.setValue=this._setValue_unavailable,!t){pt("PropertyBinding: No target node found for track: "+this.path+".");return}if(n){let l=e.objectIndex;switch(n){case"materials":if(!t.material){ot("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!t.material.materials){ot("PropertyBinding: Can not bind to material.materials as node.material does not have a materials array.",this);return}t=t.material.materials;break;case"bones":if(!t.skeleton){ot("PropertyBinding: Can not bind to bones as node does not have a skeleton.",this);return}t=t.skeleton.bones;for(let u=0;u<t.length;u++)if(t[u].name===l){l=u;break}break;case"map":if("map"in t){t=t.map;break}if(!t.material){ot("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!t.material.map){ot("PropertyBinding: Can not bind to material.map as node.material does not have a map.",this);return}t=t.material.map;break;default:if(t[n]===void 0){ot("PropertyBinding: Can not bind to objectName of node undefined.",this);return}t=t[n]}if(l!==void 0){if(t[l]===void 0){ot("PropertyBinding: Trying to bind to objectIndex of objectName, but is undefined.",this,t);return}t=t[l]}}let o=t[s];if(o===void 0){let l=e.nodeName;ot("PropertyBinding: Trying to update property for track: "+l+"."+s+" but it wasn't found.",t);return}let a=this.Versioning.None;this.targetObject=t,t.isMaterial===!0?a=this.Versioning.NeedsUpdate:t.isObject3D===!0&&(a=this.Versioning.MatrixWorldNeedsUpdate);let c=this.BindingType.Direct;if(r!==void 0){if(s==="morphTargetInfluences"){if(!t.geometry){ot("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.",this);return}if(!t.geometry.morphAttributes){ot("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.morphAttributes.",this);return}t.morphTargetDictionary[r]!==void 0&&(r=t.morphTargetDictionary[r])}c=this.BindingType.ArrayElement,this.resolvedProperty=o,this.propertyIndex=r}else o.fromArray!==void 0&&o.toArray!==void 0?(c=this.BindingType.HasFromToArray,this.resolvedProperty=o):Array.isArray(o)?(c=this.BindingType.EntireArray,this.resolvedProperty=o):this.propertyName=s;this.getValue=this.GetterByBindingType[c],this.setValue=this.SetterByBindingTypeAndVersioning[c][a]}unbind(){this.node=null,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}};it.Composite=os;it.prototype.BindingType={Direct:0,EntireArray:1,ArrayElement:2,HasFromToArray:3};it.prototype.Versioning={None:0,NeedsUpdate:1,MatrixWorldNeedsUpdate:2};it.prototype.GetterByBindingType=[it.prototype._getValue_direct,it.prototype._getValue_array,it.prototype._getValue_arrayElement,it.prototype._getValue_toArray];it.prototype.SetterByBindingTypeAndVersioning=[[it.prototype._setValue_direct,it.prototype._setValue_direct_setNeedsUpdate,it.prototype._setValue_direct_setMatrixWorldNeedsUpdate],[it.prototype._setValue_array,it.prototype._setValue_array_setNeedsUpdate,it.prototype._setValue_array_setMatrixWorldNeedsUpdate],[it.prototype._setValue_arrayElement,it.prototype._setValue_arrayElement_setNeedsUpdate,it.prototype._setValue_arrayElement_setMatrixWorldNeedsUpdate],[it.prototype._setValue_fromArray,it.prototype._setValue_fromArray_setNeedsUpdate,it.prototype._setValue_fromArray_setMatrixWorldNeedsUpdate]];var td=new Float32Array(1);var as=class i{static{p(this,"Matrix2")}static{i.prototype.isMatrix2=!0}constructor(t,e,n,s){this.elements=[1,0,0,1],t!==void 0&&this.set(t,e,n,s)}identity(){return this.set(1,0,0,1),this}fromArray(t,e=0){for(let n=0;n<4;n++)this.elements[n]=t[n+e];return this}set(t,e,n,s){let r=this.elements;return r[0]=t,r[2]=e,r[1]=n,r[3]=s,this}};typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("register",{detail:{revision:"185"}}));typeof window<"u"&&(window.__THREE__?pt("WARNING: Multiple instances of Three.js being imported."):window.__THREE__="185");var uc=`#ifdef USE_ALPHAHASH
	if ( diffuseColor.a < getAlphaHashThreshold( vPosition ) ) discard;
#endif`,hc=`#ifdef USE_ALPHAHASH
	const float ALPHA_HASH_SCALE = 0.05;
	float hash2D( vec2 value ) {
		return fract( 1.0e4 * sin( 17.0 * value.x + 0.1 * value.y ) * ( 0.1 + abs( sin( 13.0 * value.y + value.x ) ) ) );
	}
	float hash3D( vec3 value ) {
		return hash2D( vec2( hash2D( value.xy ), value.z ) );
	}
	float getAlphaHashThreshold( vec3 position ) {
		float maxDeriv = max(
			length( dFdx( position.xyz ) ),
			length( dFdy( position.xyz ) )
		);
		float pixScale = 1.0 / ( ALPHA_HASH_SCALE * maxDeriv );
		vec2 pixScales = vec2(
			exp2( floor( log2( pixScale ) ) ),
			exp2( ceil( log2( pixScale ) ) )
		);
		vec2 alpha = vec2(
			hash3D( floor( pixScales.x * position.xyz ) ),
			hash3D( floor( pixScales.y * position.xyz ) )
		);
		float lerpFactor = fract( log2( pixScale ) );
		float x = ( 1.0 - lerpFactor ) * alpha.x + lerpFactor * alpha.y;
		float a = min( lerpFactor, 1.0 - lerpFactor );
		vec3 cases = vec3(
			x * x / ( 2.0 * a * ( 1.0 - a ) ),
			( x - 0.5 * a ) / ( 1.0 - a ),
			1.0 - ( ( 1.0 - x ) * ( 1.0 - x ) / ( 2.0 * a * ( 1.0 - a ) ) )
		);
		float threshold = ( x < ( 1.0 - a ) )
			? ( ( x < a ) ? cases.x : cases.y )
			: cases.z;
		return clamp( threshold , 1.0e-6, 1.0 );
	}
#endif`,fc=`#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, vAlphaMapUv ).g;
#endif`,dc=`#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,pc=`#ifdef USE_ALPHATEST
	#ifdef ALPHA_TO_COVERAGE
	diffuseColor.a = smoothstep( alphaTest, alphaTest + fwidth( diffuseColor.a ), diffuseColor.a );
	if ( diffuseColor.a == 0.0 ) discard;
	#else
	if ( diffuseColor.a < alphaTest ) discard;
	#endif
#endif`,mc=`#ifdef USE_ALPHATEST
	uniform float alphaTest;
#endif`,gc=`#ifdef USE_AOMAP
	float ambientOcclusion = ( texture2D( aoMap, vAoMapUv ).r - 1.0 ) * aoMapIntensity + 1.0;
	reflectedLight.indirectDiffuse *= ambientOcclusion;
	#if defined( USE_CLEARCOAT ) 
		clearcoatSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_SHEEN ) 
		sheenSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_ENVMAP ) && defined( STANDARD )
		float dotNV = saturate( dot( geometryNormal, geometryViewDir ) );
		reflectedLight.indirectSpecular *= computeSpecularOcclusion( dotNV, ambientOcclusion, material.roughness );
	#endif
#endif`,xc=`#ifdef USE_AOMAP
	uniform sampler2D aoMap;
	uniform float aoMapIntensity;
#endif`,_c=`#ifdef USE_BATCHING
	#if ! defined( GL_ANGLE_multi_draw )
	#define gl_DrawID _gl_DrawID
	uniform int _gl_DrawID;
	#endif
	uniform highp sampler2D batchingTexture;
	uniform highp usampler2D batchingIdTexture;
	mat4 getBatchingMatrix( const in float i ) {
		int size = textureSize( batchingTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( batchingTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( batchingTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( batchingTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( batchingTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
	float getIndirectIndex( const in int i ) {
		int size = textureSize( batchingIdTexture, 0 ).x;
		int x = i % size;
		int y = i / size;
		return float( texelFetch( batchingIdTexture, ivec2( x, y ), 0 ).r );
	}
#endif
#ifdef USE_BATCHING_COLOR
	uniform sampler2D batchingColorTexture;
	vec4 getBatchingColor( const in float i ) {
		int size = textureSize( batchingColorTexture, 0 ).x;
		int j = int( i );
		int x = j % size;
		int y = j / size;
		return texelFetch( batchingColorTexture, ivec2( x, y ), 0 );
	}
#endif`,yc=`#ifdef USE_BATCHING
	mat4 batchingMatrix = getBatchingMatrix( getIndirectIndex( gl_DrawID ) );
#endif`,vc=`vec3 transformed = vec3( position );
#ifdef USE_ALPHAHASH
	vPosition = vec3( position );
#endif`,Mc=`vec3 objectNormal = vec3( normal );
#ifdef USE_TANGENT
	vec3 objectTangent = vec3( tangent.xyz );
#endif`,bc=`float G_BlinnPhong_Implicit( ) {
	return 0.25;
}
float D_BlinnPhong( const in float shininess, const in float dotNH ) {
	return RECIPROCAL_PI * ( shininess * 0.5 + 1.0 ) * pow( dotNH, shininess );
}
vec3 BRDF_BlinnPhong( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in vec3 specularColor, const in float shininess ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( specularColor, 1.0, dotVH );
	float G = G_BlinnPhong_Implicit( );
	float D = D_BlinnPhong( shininess, dotNH );
	return F * ( G * D );
} // validated`,Sc=`#ifdef USE_IRIDESCENCE
	const mat3 XYZ_TO_REC709 = mat3(
		 3.2404542, -0.9692660,  0.0556434,
		-1.5371385,  1.8760108, -0.2040259,
		-0.4985314,  0.0415560,  1.0572252
	);
	vec3 Fresnel0ToIor( vec3 fresnel0 ) {
		vec3 sqrtF0 = sqrt( fresnel0 );
		return ( vec3( 1.0 ) + sqrtF0 ) / ( vec3( 1.0 ) - sqrtF0 );
	}
	vec3 IorToFresnel0( vec3 transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - vec3( incidentIor ) ) / ( transmittedIor + vec3( incidentIor ) ) );
	}
	float IorToFresnel0( float transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - incidentIor ) / ( transmittedIor + incidentIor ));
	}
	vec3 evalSensitivity( float OPD, vec3 shift ) {
		float phase = 2.0 * PI * OPD * 1.0e-9;
		vec3 val = vec3( 5.4856e-13, 4.4201e-13, 5.2481e-13 );
		vec3 pos = vec3( 1.6810e+06, 1.7953e+06, 2.2084e+06 );
		vec3 var = vec3( 4.3278e+09, 9.3046e+09, 6.6121e+09 );
		vec3 xyz = val * sqrt( 2.0 * PI * var ) * cos( pos * phase + shift ) * exp( - pow2( phase ) * var );
		xyz.x += 9.7470e-14 * sqrt( 2.0 * PI * 4.5282e+09 ) * cos( 2.2399e+06 * phase + shift[ 0 ] ) * exp( - 4.5282e+09 * pow2( phase ) );
		xyz /= 1.0685e-7;
		vec3 rgb = XYZ_TO_REC709 * xyz;
		return rgb;
	}
	vec3 evalIridescence( float outsideIOR, float eta2, float cosTheta1, float thinFilmThickness, vec3 baseF0 ) {
		vec3 I;
		float iridescenceIOR = mix( outsideIOR, eta2, smoothstep( 0.0, 0.03, thinFilmThickness ) );
		float sinTheta2Sq = pow2( outsideIOR / iridescenceIOR ) * ( 1.0 - pow2( cosTheta1 ) );
		float cosTheta2Sq = 1.0 - sinTheta2Sq;
		if ( cosTheta2Sq < 0.0 ) {
			return vec3( 1.0 );
		}
		float cosTheta2 = sqrt( cosTheta2Sq );
		float R0 = IorToFresnel0( iridescenceIOR, outsideIOR );
		float R12 = F_Schlick( R0, 1.0, cosTheta1 );
		float T121 = 1.0 - R12;
		float phi12 = 0.0;
		if ( iridescenceIOR < outsideIOR ) phi12 = PI;
		float phi21 = PI - phi12;
		vec3 baseIOR = Fresnel0ToIor( clamp( baseF0, 0.0, 0.9999 ) );		vec3 R1 = IorToFresnel0( baseIOR, iridescenceIOR );
		vec3 R23 = F_Schlick( R1, 1.0, cosTheta2 );
		vec3 phi23 = vec3( 0.0 );
		if ( baseIOR[ 0 ] < iridescenceIOR ) phi23[ 0 ] = PI;
		if ( baseIOR[ 1 ] < iridescenceIOR ) phi23[ 1 ] = PI;
		if ( baseIOR[ 2 ] < iridescenceIOR ) phi23[ 2 ] = PI;
		float OPD = 2.0 * iridescenceIOR * thinFilmThickness * cosTheta2;
		vec3 phi = vec3( phi21 ) + phi23;
		vec3 R123 = clamp( R12 * R23, 1e-5, 0.9999 );
		vec3 r123 = sqrt( R123 );
		vec3 Rs = pow2( T121 ) * R23 / ( vec3( 1.0 ) - R123 );
		vec3 C0 = R12 + Rs;
		I = C0;
		vec3 Cm = Rs - T121;
		for ( int m = 1; m <= 2; ++ m ) {
			Cm *= r123;
			vec3 Sm = 2.0 * evalSensitivity( float( m ) * OPD, float( m ) * phi );
			I += Cm * Sm;
		}
		return max( I, vec3( 0.0 ) );
	}
#endif`,Ac=`#ifdef USE_BUMPMAP
	uniform sampler2D bumpMap;
	uniform float bumpScale;
	vec2 dHdxy_fwd() {
		vec2 dSTdx = dFdx( vBumpMapUv );
		vec2 dSTdy = dFdy( vBumpMapUv );
		float Hll = bumpScale * texture2D( bumpMap, vBumpMapUv ).x;
		float dBx = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdx ).x - Hll;
		float dBy = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdy ).x - Hll;
		return vec2( dBx, dBy );
	}
	vec3 perturbNormalArb( vec3 surf_pos, vec3 surf_norm, vec2 dHdxy, float faceDirection ) {
		vec3 vSigmaX = normalize( dFdx( surf_pos.xyz ) );
		vec3 vSigmaY = normalize( dFdy( surf_pos.xyz ) );
		vec3 vN = surf_norm;
		vec3 R1 = cross( vSigmaY, vN );
		vec3 R2 = cross( vN, vSigmaX );
		float fDet = dot( vSigmaX, R1 ) * faceDirection;
		vec3 vGrad = sign( fDet ) * ( dHdxy.x * R1 + dHdxy.y * R2 );
		return normalize( abs( fDet ) * surf_norm - vGrad );
	}
#endif`,wc=`#if NUM_CLIPPING_PLANES > 0
	vec4 plane;
	#ifdef ALPHA_TO_COVERAGE
		float distanceToPlane, distanceGradient;
		float clipOpacity = 1.0;
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
			distanceGradient = fwidth( distanceToPlane ) / 2.0;
			clipOpacity *= smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			if ( clipOpacity == 0.0 ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			float unionClipOpacity = 1.0;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
				distanceGradient = fwidth( distanceToPlane ) / 2.0;
				unionClipOpacity *= 1.0 - smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			}
			#pragma unroll_loop_end
			clipOpacity *= 1.0 - unionClipOpacity;
		#endif
		diffuseColor.a *= clipOpacity;
		if ( diffuseColor.a == 0.0 ) discard;
	#else
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			if ( dot( vClipPosition, plane.xyz ) > plane.w ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			bool clipped = true;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				clipped = ( dot( vClipPosition, plane.xyz ) > plane.w ) && clipped;
			}
			#pragma unroll_loop_end
			if ( clipped ) discard;
		#endif
	#endif
#endif`,Tc=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
	uniform vec4 clippingPlanes[ NUM_CLIPPING_PLANES ];
#endif`,Ec=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
#endif`,Cc=`#if NUM_CLIPPING_PLANES > 0
	vClipPosition = - mvPosition.xyz;
#endif`,Rc=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	diffuseColor *= vColor;
#endif`,Ic=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#endif`,Pc=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	varying vec4 vColor;
#endif`,Lc=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	vColor = vec4( 1.0 );
#endif
#ifdef USE_COLOR_ALPHA
	vColor *= color;
#elif defined( USE_COLOR )
	vColor.rgb *= color;
#endif
#ifdef USE_INSTANCING_COLOR
	vColor.rgb *= instanceColor.rgb;
#endif
#ifdef USE_BATCHING_COLOR
	vColor *= getBatchingColor( getIndirectIndex( gl_DrawID ) );
#endif`,Nc=`#define PI 3.141592653589793
#define PI2 6.283185307179586
#define PI_HALF 1.5707963267948966
#define RECIPROCAL_PI 0.3183098861837907
#define RECIPROCAL_PI2 0.15915494309189535
#define EPSILON 1e-6
#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
#define whiteComplement( a ) ( 1.0 - saturate( a ) )
float pow2( const in float x ) { return x*x; }
vec3 pow2( const in vec3 x ) { return x*x; }
float pow3( const in float x ) { return x*x*x; }
float pow4( const in float x ) { float x2 = x*x; return x2*x2; }
float max3( const in vec3 v ) { return max( max( v.x, v.y ), v.z ); }
float average( const in vec3 v ) { return dot( v, vec3( 0.3333333 ) ); }
highp float rand( const in vec2 uv ) {
	const highp float a = 12.9898, b = 78.233, c = 43758.5453;
	highp float dt = dot( uv.xy, vec2( a,b ) ), sn = mod( dt, PI );
	return fract( sin( sn ) * c );
}
#ifdef HIGH_PRECISION
	float precisionSafeLength( vec3 v ) { return length( v ); }
#else
	float precisionSafeLength( vec3 v ) {
		float maxComponent = max3( abs( v ) );
		return length( v / maxComponent ) * maxComponent;
	}
#endif
struct IncidentLight {
	vec3 color;
	vec3 direction;
	bool visible;
};
struct ReflectedLight {
	vec3 directDiffuse;
	vec3 directSpecular;
	vec3 indirectDiffuse;
	vec3 indirectSpecular;
};
#ifdef USE_ALPHAHASH
	varying vec3 vPosition;
#endif
vec3 transformDirection( in vec3 dir, in mat4 matrix ) {
	return normalize( ( matrix * vec4( dir, 0.0 ) ).xyz );
}
#define inverseTransformDirection transformDirectionByInverseViewMatrix
vec3 transformNormalByInverseViewMatrix( in vec3 normal, in mat4 viewMatrix ) {
	return normalize( ( vec4( normal, 0.0 ) * viewMatrix ).xyz );
}
vec3 transformDirectionByInverseViewMatrix( in vec3 dir, in mat4 viewMatrix ) {
	return normalize( ( vec4( dir, 0.0 ) * viewMatrix ).xyz );
}
bool isPerspectiveMatrix( mat4 m ) {
	return m[ 2 ][ 3 ] == - 1.0;
}
vec2 equirectUv( in vec3 dir ) {
	float u = atan( dir.z, dir.x ) * RECIPROCAL_PI2 + 0.5;
	float v = asin( clamp( dir.y, - 1.0, 1.0 ) ) * RECIPROCAL_PI + 0.5;
	return vec2( u, v );
}
vec3 BRDF_Lambert( const in vec3 diffuseColor ) {
	return RECIPROCAL_PI * diffuseColor;
}
vec3 F_Schlick( const in vec3 f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
}
float F_Schlick( const in float f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
} // validated`,Dc=`#ifdef ENVMAP_TYPE_CUBE_UV
	#define cubeUV_minMipLevel 4.0
	#define cubeUV_minTileSize 16.0
	float getFace( vec3 direction ) {
		vec3 absDirection = abs( direction );
		float face = - 1.0;
		if ( absDirection.x > absDirection.z ) {
			if ( absDirection.x > absDirection.y )
				face = direction.x > 0.0 ? 0.0 : 3.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		} else {
			if ( absDirection.z > absDirection.y )
				face = direction.z > 0.0 ? 2.0 : 5.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		}
		return face;
	}
	vec2 getUV( vec3 direction, float face ) {
		vec2 uv;
		if ( face == 0.0 ) {
			uv = vec2( direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 1.0 ) {
			uv = vec2( - direction.x, - direction.z ) / abs( direction.y );
		} else if ( face == 2.0 ) {
			uv = vec2( - direction.x, direction.y ) / abs( direction.z );
		} else if ( face == 3.0 ) {
			uv = vec2( - direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 4.0 ) {
			uv = vec2( - direction.x, direction.z ) / abs( direction.y );
		} else {
			uv = vec2( direction.x, direction.y ) / abs( direction.z );
		}
		return 0.5 * ( uv + 1.0 );
	}
	vec3 bilinearCubeUV( sampler2D envMap, vec3 direction, float mipInt ) {
		float face = getFace( direction );
		float filterInt = max( cubeUV_minMipLevel - mipInt, 0.0 );
		mipInt = max( mipInt, cubeUV_minMipLevel );
		float faceSize = exp2( mipInt );
		highp vec2 uv = getUV( direction, face ) * ( faceSize - 2.0 ) + 1.0;
		if ( face > 2.0 ) {
			uv.y += faceSize;
			face -= 3.0;
		}
		uv.x += face * faceSize;
		uv.x += filterInt * 3.0 * cubeUV_minTileSize;
		uv.y += 4.0 * ( exp2( CUBEUV_MAX_MIP ) - faceSize );
		uv.x *= CUBEUV_TEXEL_WIDTH;
		uv.y *= CUBEUV_TEXEL_HEIGHT;
		#ifdef texture2DGradEXT
			return texture2DGradEXT( envMap, uv, vec2( 0.0 ), vec2( 0.0 ) ).rgb;
		#else
			return texture2D( envMap, uv ).rgb;
		#endif
	}
	#define cubeUV_r0 1.0
	#define cubeUV_m0 - 2.0
	#define cubeUV_r1 0.8
	#define cubeUV_m1 - 1.0
	#define cubeUV_r4 0.4
	#define cubeUV_m4 2.0
	#define cubeUV_r5 0.305
	#define cubeUV_m5 3.0
	#define cubeUV_r6 0.21
	#define cubeUV_m6 4.0
	float roughnessToMip( float roughness ) {
		float mip = 0.0;
		if ( roughness >= cubeUV_r1 ) {
			mip = ( cubeUV_r0 - roughness ) * ( cubeUV_m1 - cubeUV_m0 ) / ( cubeUV_r0 - cubeUV_r1 ) + cubeUV_m0;
		} else if ( roughness >= cubeUV_r4 ) {
			mip = ( cubeUV_r1 - roughness ) * ( cubeUV_m4 - cubeUV_m1 ) / ( cubeUV_r1 - cubeUV_r4 ) + cubeUV_m1;
		} else if ( roughness >= cubeUV_r5 ) {
			mip = ( cubeUV_r4 - roughness ) * ( cubeUV_m5 - cubeUV_m4 ) / ( cubeUV_r4 - cubeUV_r5 ) + cubeUV_m4;
		} else if ( roughness >= cubeUV_r6 ) {
			mip = ( cubeUV_r5 - roughness ) * ( cubeUV_m6 - cubeUV_m5 ) / ( cubeUV_r5 - cubeUV_r6 ) + cubeUV_m5;
		} else {
			mip = - 2.0 * log2( 1.16 * roughness );		}
		return mip;
	}
	vec4 textureCubeUV( sampler2D envMap, vec3 sampleDir, float roughness ) {
		float mip = clamp( roughnessToMip( roughness ), cubeUV_m0, CUBEUV_MAX_MIP );
		float mipF = fract( mip );
		float mipInt = floor( mip );
		vec3 color0 = bilinearCubeUV( envMap, sampleDir, mipInt );
		if ( mipF == 0.0 ) {
			return vec4( color0, 1.0 );
		} else {
			vec3 color1 = bilinearCubeUV( envMap, sampleDir, mipInt + 1.0 );
			return vec4( mix( color0, color1, mipF ), 1.0 );
		}
	}
#endif`,Uc=`vec3 transformedNormal = objectNormal;
#ifdef USE_TANGENT
	vec3 transformedTangent = objectTangent;
#endif
#ifdef USE_BATCHING
	mat3 bm = mat3( batchingMatrix );
	transformedNormal /= vec3( dot( bm[ 0 ], bm[ 0 ] ), dot( bm[ 1 ], bm[ 1 ] ), dot( bm[ 2 ], bm[ 2 ] ) );
	transformedNormal = bm * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = bm * transformedTangent;
	#endif
#endif
#ifdef USE_INSTANCING
	mat3 im = mat3( instanceMatrix );
	transformedNormal /= vec3( dot( im[ 0 ], im[ 0 ] ), dot( im[ 1 ], im[ 1 ] ), dot( im[ 2 ], im[ 2 ] ) );
	transformedNormal = im * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = im * transformedTangent;
	#endif
#endif
transformedNormal = normalMatrix * transformedNormal;
#ifdef FLIP_SIDED
	transformedNormal = - transformedNormal;
#endif
#ifdef USE_TANGENT
	transformedTangent = ( modelViewMatrix * vec4( transformedTangent, 0.0 ) ).xyz;
#endif`,Fc=`#ifdef USE_DISPLACEMENTMAP
	uniform sampler2D displacementMap;
	uniform float displacementScale;
	uniform float displacementBias;
#endif`,Oc=`#ifdef USE_DISPLACEMENTMAP
	transformed += normalize( objectNormal ) * ( texture2D( displacementMap, vDisplacementMapUv ).x * displacementScale + displacementBias );
#endif`,Bc=`#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
	#ifdef DECODE_VIDEO_TEXTURE_EMISSIVE
		emissiveColor = sRGBTransferEOTF( emissiveColor );
	#endif
	totalEmissiveRadiance *= emissiveColor.rgb;
#endif`,zc=`#ifdef USE_EMISSIVEMAP
	uniform sampler2D emissiveMap;
#endif`,kc="gl_FragColor = linearToOutputTexel( gl_FragColor );",Vc=`vec4 LinearTransferOETF( in vec4 value ) {
	return value;
}
vec4 sRGBTransferEOTF( in vec4 value ) {
	return vec4( mix( pow( value.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), value.rgb * 0.0773993808, vec3( lessThanEqual( value.rgb, vec3( 0.04045 ) ) ) ), value.a );
}
vec4 sRGBTransferOETF( in vec4 value ) {
	return vec4( mix( pow( value.rgb, vec3( 0.41666 ) ) * 1.055 - vec3( 0.055 ), value.rgb * 12.92, vec3( lessThanEqual( value.rgb, vec3( 0.0031308 ) ) ) ), value.a );
}`,Gc=`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vec3 cameraToFrag;
		if ( isOrthographic ) {
			cameraToFrag = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToFrag = normalize( vWorldPosition - cameraPosition );
		}
		vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vec3 reflectVec = reflect( cameraToFrag, worldNormal );
		#else
			vec3 reflectVec = refract( cameraToFrag, worldNormal, refractionRatio );
		#endif
	#else
		vec3 reflectVec = vReflect;
	#endif
	#ifdef ENVMAP_TYPE_CUBE
		vec4 envColor = textureCube( envMap, envMapRotation * reflectVec );
		#ifdef ENVMAP_BLENDING_MULTIPLY
			outgoingLight = mix( outgoingLight, outgoingLight * envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_MIX )
			outgoingLight = mix( outgoingLight, envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_ADD )
			outgoingLight += envColor.xyz * specularStrength * reflectivity;
		#endif
	#endif
#endif`,Hc=`#ifdef USE_ENVMAP
	uniform float envMapIntensity;
	uniform mat3 envMapRotation;
	#ifdef ENVMAP_TYPE_CUBE
		uniform samplerCube envMap;
	#else
		uniform sampler2D envMap;
	#endif
#endif`,Wc=`#ifdef USE_ENVMAP
	uniform float reflectivity;
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		varying vec3 vWorldPosition;
		uniform float refractionRatio;
	#else
		varying vec3 vReflect;
	#endif
#endif`,Xc=`#ifdef USE_ENVMAP
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		
		varying vec3 vWorldPosition;
	#else
		varying vec3 vReflect;
		uniform float refractionRatio;
	#endif
#endif`,qc=`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vWorldPosition = worldPosition.xyz;
	#else
		vec3 cameraToVertex;
		if ( isOrthographic ) {
			cameraToVertex = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToVertex = normalize( worldPosition.xyz - cameraPosition );
		}
		vec3 worldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vReflect = reflect( cameraToVertex, worldNormal );
		#else
			vReflect = refract( cameraToVertex, worldNormal, refractionRatio );
		#endif
	#endif
#endif`,$c=`#ifdef USE_FOG
	vFogDepth = - mvPosition.z;
#endif`,Yc=`#ifdef USE_FOG
	varying float vFogDepth;
#endif`,Zc=`#ifdef USE_FOG
	#ifdef FOG_EXP2
		float fogFactor = 1.0 - exp( - fogDensity * fogDensity * vFogDepth * vFogDepth );
	#else
		float fogFactor = smoothstep( fogNear, fogFar, vFogDepth );
	#endif
	gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );
#endif`,Jc=`#ifdef USE_FOG
	uniform vec3 fogColor;
	varying float vFogDepth;
	#ifdef FOG_EXP2
		uniform float fogDensity;
	#else
		uniform float fogNear;
		uniform float fogFar;
	#endif
#endif`,Kc=`#ifdef USE_GRADIENTMAP
	uniform sampler2D gradientMap;
#endif
vec3 getGradientIrradiance( vec3 normal, vec3 lightDirection ) {
	float dotNL = dot( normal, lightDirection );
	vec2 coord = vec2( dotNL * 0.5 + 0.5, 0.0 );
	#ifdef USE_GRADIENTMAP
		return vec3( texture2D( gradientMap, coord ).r );
	#else
		vec2 fw = fwidth( coord ) * 0.5;
		return mix( vec3( 0.7 ), vec3( 1.0 ), smoothstep( 0.7 - fw.x, 0.7 + fw.x, coord.x ) );
	#endif
}`,jc=`#ifdef USE_LIGHTMAP
	uniform sampler2D lightMap;
	uniform float lightMapIntensity;
#endif`,Qc=`LambertMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularStrength = specularStrength;`,tl=`varying vec3 vViewPosition;
struct LambertMaterial {
	vec3 diffuseColor;
	float specularStrength;
};
void RE_Direct_Lambert( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Lambert( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Lambert
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Lambert`,el=`uniform bool receiveShadow;
uniform vec3 ambientLightColor;
#if defined( USE_LIGHT_PROBES )
	uniform vec3 lightProbe[ 9 ];
#endif
vec3 shGetIrradianceAt( in vec3 normal, in vec3 shCoefficients[ 9 ] ) {
	float x = normal.x, y = normal.y, z = normal.z;
	vec3 result = shCoefficients[ 0 ] * 0.886227;
	result += shCoefficients[ 1 ] * 2.0 * 0.511664 * y;
	result += shCoefficients[ 2 ] * 2.0 * 0.511664 * z;
	result += shCoefficients[ 3 ] * 2.0 * 0.511664 * x;
	result += shCoefficients[ 4 ] * 2.0 * 0.429043 * x * y;
	result += shCoefficients[ 5 ] * 2.0 * 0.429043 * y * z;
	result += shCoefficients[ 6 ] * ( 0.743125 * z * z - 0.247708 );
	result += shCoefficients[ 7 ] * 2.0 * 0.429043 * x * z;
	result += shCoefficients[ 8 ] * 0.429043 * ( x * x - y * y );
	return result;
}
vec3 getLightProbeIrradiance( const in vec3 lightProbe[ 9 ], const in vec3 normal ) {
	vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
	vec3 irradiance = shGetIrradianceAt( worldNormal, lightProbe );
	return irradiance;
}
vec3 getAmbientLightIrradiance( const in vec3 ambientLightColor ) {
	vec3 irradiance = ambientLightColor;
	return irradiance;
}
float getDistanceAttenuation( const in float lightDistance, const in float cutoffDistance, const in float decayExponent ) {
	float distanceFalloff = 1.0 / max( pow( lightDistance, decayExponent ), 0.01 );
	if ( cutoffDistance > 0.0 ) {
		distanceFalloff *= pow2( saturate( 1.0 - pow4( lightDistance / cutoffDistance ) ) );
	}
	return distanceFalloff;
}
float getSpotAttenuation( const in float coneCosine, const in float penumbraCosine, const in float angleCosine ) {
	return smoothstep( coneCosine, penumbraCosine, angleCosine );
}
#if NUM_DIR_LIGHTS > 0
	struct DirectionalLight {
		vec3 direction;
		vec3 color;
	};
	uniform DirectionalLight directionalLights[ NUM_DIR_LIGHTS ];
	void getDirectionalLightInfo( const in DirectionalLight directionalLight, out IncidentLight light ) {
		light.color = directionalLight.color;
		light.direction = directionalLight.direction;
		light.visible = true;
	}
#endif
#if NUM_POINT_LIGHTS > 0
	struct PointLight {
		vec3 position;
		vec3 color;
		float distance;
		float decay;
	};
	uniform PointLight pointLights[ NUM_POINT_LIGHTS ];
	void getPointLightInfo( const in PointLight pointLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = pointLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float lightDistance = length( lVector );
		light.color = pointLight.color;
		light.color *= getDistanceAttenuation( lightDistance, pointLight.distance, pointLight.decay );
		light.visible = ( light.color != vec3( 0.0 ) );
	}
#endif
#if NUM_SPOT_LIGHTS > 0
	struct SpotLight {
		vec3 position;
		vec3 direction;
		vec3 color;
		float distance;
		float decay;
		float coneCos;
		float penumbraCos;
	};
	uniform SpotLight spotLights[ NUM_SPOT_LIGHTS ];
	void getSpotLightInfo( const in SpotLight spotLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = spotLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float angleCos = dot( light.direction, spotLight.direction );
		float spotAttenuation = getSpotAttenuation( spotLight.coneCos, spotLight.penumbraCos, angleCos );
		if ( spotAttenuation > 0.0 ) {
			float lightDistance = length( lVector );
			light.color = spotLight.color * spotAttenuation;
			light.color *= getDistanceAttenuation( lightDistance, spotLight.distance, spotLight.decay );
			light.visible = ( light.color != vec3( 0.0 ) );
		} else {
			light.color = vec3( 0.0 );
			light.visible = false;
		}
	}
#endif
#if NUM_RECT_AREA_LIGHTS > 0
	struct RectAreaLight {
		vec3 color;
		vec3 position;
		vec3 halfWidth;
		vec3 halfHeight;
	};
	uniform sampler2D ltc_1;	uniform sampler2D ltc_2;
	uniform RectAreaLight rectAreaLights[ NUM_RECT_AREA_LIGHTS ];
#endif
#if NUM_HEMI_LIGHTS > 0
	struct HemisphereLight {
		vec3 direction;
		vec3 skyColor;
		vec3 groundColor;
	};
	uniform HemisphereLight hemisphereLights[ NUM_HEMI_LIGHTS ];
	vec3 getHemisphereLightIrradiance( const in HemisphereLight hemiLight, const in vec3 normal ) {
		float dotNL = dot( normal, hemiLight.direction );
		float hemiDiffuseWeight = 0.5 * dotNL + 0.5;
		vec3 irradiance = mix( hemiLight.groundColor, hemiLight.skyColor, hemiDiffuseWeight );
		return irradiance;
	}
#endif
#include <lightprobes_pars_fragment>`,nl=`#ifdef USE_ENVMAP
	vec3 getIBLIrradiance( const in vec3 normal ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * worldNormal, 1.0 );
			return PI * envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	vec3 getIBLRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 reflectVec = reflect( - viewDir, normal );
			reflectVec = normalize( mix( reflectVec, normal, pow4( roughness ) ) );
			reflectVec = transformDirectionByInverseViewMatrix( reflectVec, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * reflectVec, roughness );
			return envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	#ifdef USE_ANISOTROPY
		vec3 getIBLAnisotropyRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness, const in vec3 bitangent, const in float anisotropy ) {
			#ifdef ENVMAP_TYPE_CUBE_UV
				vec3 bentNormal = cross( bitangent, viewDir );
				bentNormal = normalize( cross( bentNormal, bitangent ) );
				bentNormal = normalize( mix( bentNormal, normal, pow2( pow2( 1.0 - anisotropy * ( 1.0 - roughness ) ) ) ) );
				return getIBLRadiance( viewDir, bentNormal, roughness );
			#else
				return vec3( 0.0 );
			#endif
		}
	#endif
#endif`,il=`ToonMaterial material;
material.diffuseColor = diffuseColor.rgb;`,sl=`varying vec3 vViewPosition;
struct ToonMaterial {
	vec3 diffuseColor;
};
void RE_Direct_Toon( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 irradiance = getGradientIrradiance( geometryNormal, directLight.direction ) * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Toon( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Toon
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Toon`,rl=`BlinnPhongMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularColor = specular;
material.specularShininess = shininess;
material.specularStrength = specularStrength;`,ol=`varying vec3 vViewPosition;
struct BlinnPhongMaterial {
	vec3 diffuseColor;
	vec3 specularColor;
	float specularShininess;
	float specularStrength;
};
void RE_Direct_BlinnPhong( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
	reflectedLight.directSpecular += irradiance * BRDF_BlinnPhong( directLight.direction, geometryViewDir, geometryNormal, material.specularColor, material.specularShininess ) * material.specularStrength;
}
void RE_IndirectDiffuse_BlinnPhong( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_BlinnPhong
#define RE_IndirectDiffuse		RE_IndirectDiffuse_BlinnPhong`,al=`PhysicalMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.diffuseContribution = diffuseColor.rgb * ( 1.0 - metalnessFactor );
material.metalness = metalnessFactor;
vec3 dxy = max( abs( dFdx( nonPerturbedNormal ) ), abs( dFdy( nonPerturbedNormal ) ) );
float geometryRoughness = max( max( dxy.x, dxy.y ), dxy.z );
material.roughness = max( roughnessFactor, 0.0525 );material.roughness += geometryRoughness;
material.roughness = min( material.roughness, 1.0 );
#ifdef IOR
	material.ior = ior;
	#ifdef USE_SPECULAR
		float specularIntensityFactor = specularIntensity;
		vec3 specularColorFactor = specularColor;
		#ifdef USE_SPECULAR_COLORMAP
			specularColorFactor *= texture2D( specularColorMap, vSpecularColorMapUv ).rgb;
		#endif
		#ifdef USE_SPECULAR_INTENSITYMAP
			specularIntensityFactor *= texture2D( specularIntensityMap, vSpecularIntensityMapUv ).a;
		#endif
		material.specularF90 = mix( specularIntensityFactor, 1.0, metalnessFactor );
	#else
		float specularIntensityFactor = 1.0;
		vec3 specularColorFactor = vec3( 1.0 );
		material.specularF90 = 1.0;
	#endif
	material.specularColor = min( pow2( ( material.ior - 1.0 ) / ( material.ior + 1.0 ) ) * specularColorFactor, vec3( 1.0 ) ) * specularIntensityFactor;
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
#else
	material.specularColor = vec3( 0.04 );
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
	material.specularF90 = 1.0;
#endif
#ifdef USE_CLEARCOAT
	material.clearcoat = clearcoat;
	material.clearcoatRoughness = clearcoatRoughness;
	material.clearcoatF0 = vec3( 0.04 );
	material.clearcoatF90 = 1.0;
	#ifdef USE_CLEARCOATMAP
		material.clearcoat *= texture2D( clearcoatMap, vClearcoatMapUv ).x;
	#endif
	#ifdef USE_CLEARCOAT_ROUGHNESSMAP
		material.clearcoatRoughness *= texture2D( clearcoatRoughnessMap, vClearcoatRoughnessMapUv ).y;
	#endif
	material.clearcoat = saturate( material.clearcoat );	material.clearcoatRoughness = max( material.clearcoatRoughness, 0.0525 );
	material.clearcoatRoughness += geometryRoughness;
	material.clearcoatRoughness = min( material.clearcoatRoughness, 1.0 );
#endif
#ifdef USE_DISPERSION
	material.dispersion = dispersion;
#endif
#ifdef USE_IRIDESCENCE
	material.iridescence = iridescence;
	material.iridescenceIOR = iridescenceIOR;
	#ifdef USE_IRIDESCENCEMAP
		material.iridescence *= texture2D( iridescenceMap, vIridescenceMapUv ).r;
	#endif
	#ifdef USE_IRIDESCENCE_THICKNESSMAP
		material.iridescenceThickness = (iridescenceThicknessMaximum - iridescenceThicknessMinimum) * texture2D( iridescenceThicknessMap, vIridescenceThicknessMapUv ).g + iridescenceThicknessMinimum;
	#else
		material.iridescenceThickness = iridescenceThicknessMaximum;
	#endif
#endif
#ifdef USE_SHEEN
	material.sheenColor = sheenColor;
	#ifdef USE_SHEEN_COLORMAP
		material.sheenColor *= texture2D( sheenColorMap, vSheenColorMapUv ).rgb;
	#endif
	material.sheenRoughness = clamp( sheenRoughness, 0.0001, 1.0 );
	#ifdef USE_SHEEN_ROUGHNESSMAP
		material.sheenRoughness *= texture2D( sheenRoughnessMap, vSheenRoughnessMapUv ).a;
	#endif
#endif
#ifdef USE_ANISOTROPY
	#ifdef USE_ANISOTROPYMAP
		mat2 anisotropyMat = mat2( anisotropyVector.x, anisotropyVector.y, - anisotropyVector.y, anisotropyVector.x );
		vec3 anisotropyPolar = texture2D( anisotropyMap, vAnisotropyMapUv ).rgb;
		vec2 anisotropyV = anisotropyMat * normalize( 2.0 * anisotropyPolar.rg - vec2( 1.0 ) ) * anisotropyPolar.b;
	#else
		vec2 anisotropyV = anisotropyVector;
	#endif
	material.anisotropy = length( anisotropyV );
	if( material.anisotropy == 0.0 ) {
		anisotropyV = vec2( 1.0, 0.0 );
	} else {
		anisotropyV /= material.anisotropy;
		material.anisotropy = saturate( material.anisotropy );
	}
	material.alphaT = mix( pow2( material.roughness ), 1.0, pow2( material.anisotropy ) );
	material.anisotropyT = tbn[ 0 ] * anisotropyV.x + tbn[ 1 ] * anisotropyV.y;
	material.anisotropyB = tbn[ 1 ] * anisotropyV.x - tbn[ 0 ] * anisotropyV.y;
#endif`,cl=`uniform sampler2D dfgLUT;
struct PhysicalMaterial {
	vec3 diffuseColor;
	vec3 diffuseContribution;
	vec3 specularColor;
	vec3 specularColorBlended;
	float roughness;
	float metalness;
	float specularF90;
	float dispersion;
	#ifdef USE_CLEARCOAT
		float clearcoat;
		float clearcoatRoughness;
		vec3 clearcoatF0;
		float clearcoatF90;
	#endif
	#ifdef USE_IRIDESCENCE
		float iridescence;
		float iridescenceIOR;
		float iridescenceThickness;
		vec3 iridescenceFresnel;
		vec3 iridescenceF0;
		vec3 iridescenceFresnelDielectric;
		vec3 iridescenceFresnelMetallic;
	#endif
	#ifdef USE_SHEEN
		vec3 sheenColor;
		float sheenRoughness;
	#endif
	#ifdef IOR
		float ior;
	#endif
	#ifdef USE_TRANSMISSION
		float transmission;
		float transmissionAlpha;
		float thickness;
		float attenuationDistance;
		vec3 attenuationColor;
	#endif
	#ifdef USE_ANISOTROPY
		float anisotropy;
		float alphaT;
		vec3 anisotropyT;
		vec3 anisotropyB;
	#endif
};
vec3 clearcoatSpecularDirect = vec3( 0.0 );
vec3 clearcoatSpecularIndirect = vec3( 0.0 );
vec3 sheenSpecularDirect = vec3( 0.0 );
vec3 sheenSpecularIndirect = vec3(0.0 );
vec3 Schlick_to_F0( const in vec3 f, const in float f90, const in float dotVH ) {
    float x = clamp( 1.0 - dotVH, 0.0, 1.0 );
    float x2 = x * x;
    float x5 = clamp( x * x2 * x2, 0.0, 0.9999 );
    return ( f - vec3( f90 ) * x5 ) / ( 1.0 - x5 );
}
float V_GGX_SmithCorrelated( const in float alpha, const in float dotNL, const in float dotNV ) {
	float a2 = pow2( alpha );
	float gv = dotNL * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNV ) );
	float gl = dotNV * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNL ) );
	return 0.5 / max( gv + gl, EPSILON );
}
float D_GGX( const in float alpha, const in float dotNH ) {
	float a2 = pow2( alpha );
	float denom = pow2( dotNH ) * ( a2 - 1.0 ) + 1.0;
	return RECIPROCAL_PI * a2 / pow2( denom );
}
#ifdef USE_ANISOTROPY
	float V_GGX_SmithCorrelated_Anisotropic( const in float alphaT, const in float alphaB, const in float dotTV, const in float dotBV, const in float dotTL, const in float dotBL, const in float dotNV, const in float dotNL ) {
		float gv = dotNL * length( vec3( alphaT * dotTV, alphaB * dotBV, dotNV ) );
		float gl = dotNV * length( vec3( alphaT * dotTL, alphaB * dotBL, dotNL ) );
		return 0.5 / max( gv + gl, EPSILON );
	}
	float D_GGX_Anisotropic( const in float alphaT, const in float alphaB, const in float dotNH, const in float dotTH, const in float dotBH ) {
		float a2 = alphaT * alphaB;
		highp vec3 v = vec3( alphaB * dotTH, alphaT * dotBH, a2 * dotNH );
		highp float v2 = dot( v, v );
		float w2 = a2 / v2;
		return RECIPROCAL_PI * a2 * pow2 ( w2 );
	}
#endif
#ifdef USE_CLEARCOAT
	vec3 BRDF_GGX_Clearcoat( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material) {
		vec3 f0 = material.clearcoatF0;
		float f90 = material.clearcoatF90;
		float roughness = material.clearcoatRoughness;
		float alpha = pow2( roughness );
		vec3 halfDir = normalize( lightDir + viewDir );
		float dotNL = saturate( dot( normal, lightDir ) );
		float dotNV = saturate( dot( normal, viewDir ) );
		float dotNH = saturate( dot( normal, halfDir ) );
		float dotVH = saturate( dot( viewDir, halfDir ) );
		vec3 F = F_Schlick( f0, f90, dotVH );
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
		return F * ( V * D );
	}
#endif
vec3 BRDF_GGX( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material ) {
	vec3 f0 = material.specularColorBlended;
	float f90 = material.specularF90;
	float roughness = material.roughness;
	float alpha = pow2( roughness );
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( f0, f90, dotVH );
	#ifdef USE_IRIDESCENCE
		F = mix( F, material.iridescenceFresnel, material.iridescence );
	#endif
	#ifdef USE_ANISOTROPY
		float dotTL = dot( material.anisotropyT, lightDir );
		float dotTV = dot( material.anisotropyT, viewDir );
		float dotTH = dot( material.anisotropyT, halfDir );
		float dotBL = dot( material.anisotropyB, lightDir );
		float dotBV = dot( material.anisotropyB, viewDir );
		float dotBH = dot( material.anisotropyB, halfDir );
		float V = V_GGX_SmithCorrelated_Anisotropic( material.alphaT, alpha, dotTV, dotBV, dotTL, dotBL, dotNV, dotNL );
		float D = D_GGX_Anisotropic( material.alphaT, alpha, dotNH, dotTH, dotBH );
	#else
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
	#endif
	return F * ( V * D );
}
vec2 LTC_Uv( const in vec3 N, const in vec3 V, const in float roughness ) {
	const float LUT_SIZE = 64.0;
	const float LUT_SCALE = ( LUT_SIZE - 1.0 ) / LUT_SIZE;
	const float LUT_BIAS = 0.5 / LUT_SIZE;
	float dotNV = saturate( dot( N, V ) );
	vec2 uv = vec2( roughness, sqrt( 1.0 - dotNV ) );
	uv = uv * LUT_SCALE + LUT_BIAS;
	return uv;
}
float LTC_ClippedSphereFormFactor( const in vec3 f ) {
	float l = length( f );
	return max( ( l * l + f.z ) / ( l + 1.0 ), 0.0 );
}
vec3 LTC_EdgeVectorFormFactor( const in vec3 v1, const in vec3 v2 ) {
	float x = dot( v1, v2 );
	float y = abs( x );
	float a = 0.8543985 + ( 0.4965155 + 0.0145206 * y ) * y;
	float b = 3.4175940 + ( 4.1616724 + y ) * y;
	float v = a / b;
	float theta_sintheta = ( x > 0.0 ) ? v : 0.5 * inversesqrt( max( 1.0 - x * x, 1e-7 ) ) - v;
	return cross( v1, v2 ) * theta_sintheta;
}
vec3 LTC_Evaluate( const in vec3 N, const in vec3 V, const in vec3 P, const in mat3 mInv, const in vec3 rectCoords[ 4 ] ) {
	vec3 v1 = rectCoords[ 1 ] - rectCoords[ 0 ];
	vec3 v2 = rectCoords[ 3 ] - rectCoords[ 0 ];
	vec3 lightNormal = cross( v1, v2 );
	if( dot( lightNormal, P - rectCoords[ 0 ] ) < 0.0 ) return vec3( 0.0 );
	vec3 T1, T2;
	T1 = normalize( V - N * dot( V, N ) );
	T2 = - cross( N, T1 );
	mat3 mat = mInv * transpose( mat3( T1, T2, N ) );
	vec3 coords[ 4 ];
	coords[ 0 ] = mat * ( rectCoords[ 0 ] - P );
	coords[ 1 ] = mat * ( rectCoords[ 1 ] - P );
	coords[ 2 ] = mat * ( rectCoords[ 2 ] - P );
	coords[ 3 ] = mat * ( rectCoords[ 3 ] - P );
	coords[ 0 ] = normalize( coords[ 0 ] );
	coords[ 1 ] = normalize( coords[ 1 ] );
	coords[ 2 ] = normalize( coords[ 2 ] );
	coords[ 3 ] = normalize( coords[ 3 ] );
	vec3 vectorFormFactor = vec3( 0.0 );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 0 ], coords[ 1 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 1 ], coords[ 2 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 2 ], coords[ 3 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 3 ], coords[ 0 ] );
	float result = LTC_ClippedSphereFormFactor( vectorFormFactor );
	return vec3( result );
}
#if defined( USE_SHEEN )
float D_Charlie( float roughness, float dotNH ) {
	float alpha = pow2( roughness );
	float invAlpha = 1.0 / alpha;
	float cos2h = dotNH * dotNH;
	float sin2h = max( 1.0 - cos2h, 0.0078125 );
	return ( 2.0 + invAlpha ) * pow( sin2h, invAlpha * 0.5 ) / ( 2.0 * PI );
}
float V_Neubelt( float dotNV, float dotNL ) {
	return saturate( 1.0 / ( 4.0 * ( dotNL + dotNV - dotNL * dotNV ) ) );
}
vec3 BRDF_Sheen( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, vec3 sheenColor, const in float sheenRoughness ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float D = D_Charlie( sheenRoughness, dotNH );
	float V = V_Neubelt( dotNV, dotNL );
	return sheenColor * ( D * V );
}
#endif
float IBLSheenBRDF( const in vec3 normal, const in vec3 viewDir, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	float r2 = roughness * roughness;
	float rInv = 1.0 / ( roughness + 0.1 );
	float a = -1.9362 + 1.0678 * roughness + 0.4573 * r2 - 0.8469 * rInv;
	float b = -0.6014 + 0.5538 * roughness - 0.4670 * r2 - 0.1255 * rInv;
	float DG = exp( a * dotNV + b );
	return saturate( DG );
}
vec3 EnvironmentBRDF( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 fab = texture2D( dfgLUT, vec2( roughness, dotNV ) ).rg;
	return specularColor * fab.x + specularF90 * fab.y;
}
#ifdef USE_IRIDESCENCE
void computeMultiscatteringIridescence( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float iridescence, const in vec3 iridescenceF0, const in float roughness, inout vec3 singleScatter, inout vec3 multiScatter ) {
#else
void computeMultiscattering( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness, inout vec3 singleScatter, inout vec3 multiScatter ) {
#endif
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 fab = texture2D( dfgLUT, vec2( roughness, dotNV ) ).rg;
	#ifdef USE_IRIDESCENCE
		vec3 Fr = mix( specularColor, iridescenceF0, iridescence );
	#else
		vec3 Fr = specularColor;
	#endif
	vec3 FssEss = Fr * fab.x + specularF90 * fab.y;
	float Ess = fab.x + fab.y;
	float Ems = 1.0 - Ess;
	vec3 Favg = Fr + ( 1.0 - Fr ) * 0.047619;	vec3 Fms = FssEss * Favg / ( 1.0 - Ems * Favg );
	singleScatter += FssEss;
	multiScatter += Fms * Ems;
}
vec3 BRDF_GGX_Multiscatter( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material ) {
	vec3 singleScatter = BRDF_GGX( lightDir, viewDir, normal, material );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 dfgV = texture2D( dfgLUT, vec2( material.roughness, dotNV ) ).rg;
	vec2 dfgL = texture2D( dfgLUT, vec2( material.roughness, dotNL ) ).rg;
	vec3 FssEss_V = material.specularColorBlended * dfgV.x + material.specularF90 * dfgV.y;
	vec3 FssEss_L = material.specularColorBlended * dfgL.x + material.specularF90 * dfgL.y;
	float Ess_V = dfgV.x + dfgV.y;
	float Ess_L = dfgL.x + dfgL.y;
	float Ems_V = 1.0 - Ess_V;
	float Ems_L = 1.0 - Ess_L;
	vec3 Favg = material.specularColorBlended + ( 1.0 - material.specularColorBlended ) * 0.047619;
	vec3 Fms = FssEss_V * FssEss_L * Favg / ( 1.0 - Ems_V * Ems_L * Favg + EPSILON );
	float compensationFactor = Ems_V * Ems_L;
	vec3 multiScatter = Fms * compensationFactor;
	return singleScatter + multiScatter;
}
#if NUM_RECT_AREA_LIGHTS > 0
	void RE_Direct_RectArea_Physical( const in RectAreaLight rectAreaLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
		vec3 normal = geometryNormal;
		vec3 viewDir = geometryViewDir;
		vec3 position = geometryPosition;
		vec3 lightPos = rectAreaLight.position;
		vec3 halfWidth = rectAreaLight.halfWidth;
		vec3 halfHeight = rectAreaLight.halfHeight;
		vec3 lightColor = rectAreaLight.color;
		float roughness = material.roughness;
		vec3 rectCoords[ 4 ];
		rectCoords[ 0 ] = lightPos + halfWidth - halfHeight;		rectCoords[ 1 ] = lightPos - halfWidth - halfHeight;
		rectCoords[ 2 ] = lightPos - halfWidth + halfHeight;
		rectCoords[ 3 ] = lightPos + halfWidth + halfHeight;
		vec2 uv = LTC_Uv( normal, viewDir, roughness );
		vec4 t1 = texture2D( ltc_1, uv );
		vec4 t2 = texture2D( ltc_2, uv );
		mat3 mInv = mat3(
			vec3( t1.x, 0, t1.y ),
			vec3(    0, 1,    0 ),
			vec3( t1.z, 0, t1.w )
		);
		vec3 fresnel = ( material.specularColorBlended * t2.x + ( material.specularF90 - material.specularColorBlended ) * t2.y );
		reflectedLight.directSpecular += lightColor * fresnel * LTC_Evaluate( normal, viewDir, position, mInv, rectCoords );
		reflectedLight.directDiffuse += lightColor * material.diffuseContribution * LTC_Evaluate( normal, viewDir, position, mat3( 1.0 ), rectCoords );
		#ifdef USE_CLEARCOAT
			vec3 Ncc = geometryClearcoatNormal;
			vec2 uvClearcoat = LTC_Uv( Ncc, viewDir, material.clearcoatRoughness );
			vec4 t1Clearcoat = texture2D( ltc_1, uvClearcoat );
			vec4 t2Clearcoat = texture2D( ltc_2, uvClearcoat );
			mat3 mInvClearcoat = mat3(
				vec3( t1Clearcoat.x, 0, t1Clearcoat.y ),
				vec3(             0, 1,             0 ),
				vec3( t1Clearcoat.z, 0, t1Clearcoat.w )
			);
			vec3 fresnelClearcoat = material.clearcoatF0 * t2Clearcoat.x + ( material.clearcoatF90 - material.clearcoatF0 ) * t2Clearcoat.y;
			clearcoatSpecularDirect += lightColor * fresnelClearcoat * LTC_Evaluate( Ncc, viewDir, position, mInvClearcoat, rectCoords );
		#endif
	}
#endif
void RE_Direct_Physical( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	#ifdef USE_CLEARCOAT
		float dotNLcc = saturate( dot( geometryClearcoatNormal, directLight.direction ) );
		vec3 ccIrradiance = dotNLcc * directLight.color;
		clearcoatSpecularDirect += ccIrradiance * BRDF_GGX_Clearcoat( directLight.direction, geometryViewDir, geometryClearcoatNormal, material );
	#endif
	#ifdef USE_SHEEN
 
 		sheenSpecularDirect += irradiance * BRDF_Sheen( directLight.direction, geometryViewDir, geometryNormal, material.sheenColor, material.sheenRoughness );
 
 		float sheenAlbedoV = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
 		float sheenAlbedoL = IBLSheenBRDF( geometryNormal, directLight.direction, material.sheenRoughness );
 
 		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * max( sheenAlbedoV, sheenAlbedoL );
 
 		irradiance *= sheenEnergyComp;
 
 	#endif
	reflectedLight.directSpecular += irradiance * BRDF_GGX_Multiscatter( directLight.direction, geometryViewDir, geometryNormal, material );
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseContribution );
}
void RE_IndirectDiffuse_Physical( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 diffuse = irradiance * BRDF_Lambert( material.diffuseContribution );
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		diffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectDiffuse += diffuse;
}
void RE_IndirectSpecular_Physical( const in vec3 radiance, const in vec3 irradiance, const in vec3 clearcoatRadiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight) {
	#ifdef USE_CLEARCOAT
		clearcoatSpecularIndirect += clearcoatRadiance * EnvironmentBRDF( geometryClearcoatNormal, geometryViewDir, material.clearcoatF0, material.clearcoatF90, material.clearcoatRoughness );
	#endif
	#ifdef USE_SHEEN
		sheenSpecularIndirect += irradiance * material.sheenColor * IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness ) * RECIPROCAL_PI;
 	#endif
	vec3 singleScatteringDielectric = vec3( 0.0 );
	vec3 multiScatteringDielectric = vec3( 0.0 );
	vec3 singleScatteringMetallic = vec3( 0.0 );
	vec3 multiScatteringMetallic = vec3( 0.0 );
	#ifdef USE_IRIDESCENCE
		computeMultiscatteringIridescence( geometryNormal, geometryViewDir, material.specularColor, material.specularF90, material.iridescence, material.iridescenceFresnelDielectric, material.roughness, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscatteringIridescence( geometryNormal, geometryViewDir, material.diffuseColor, material.specularF90, material.iridescence, material.iridescenceFresnelMetallic, material.roughness, singleScatteringMetallic, multiScatteringMetallic );
	#else
		computeMultiscattering( geometryNormal, geometryViewDir, material.specularColor, material.specularF90, material.roughness, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscattering( geometryNormal, geometryViewDir, material.diffuseColor, material.specularF90, material.roughness, singleScatteringMetallic, multiScatteringMetallic );
	#endif
	vec3 singleScattering = mix( singleScatteringDielectric, singleScatteringMetallic, material.metalness );
	vec3 multiScattering = mix( multiScatteringDielectric, multiScatteringMetallic, material.metalness );
	vec3 totalScatteringDielectric = singleScatteringDielectric + multiScatteringDielectric;
	vec3 diffuse = material.diffuseContribution * ( 1.0 - totalScatteringDielectric );
	vec3 cosineWeightedIrradiance = irradiance * RECIPROCAL_PI;
	vec3 indirectSpecular = radiance * singleScattering;
	indirectSpecular += multiScattering * cosineWeightedIrradiance;
	vec3 indirectDiffuse = diffuse * cosineWeightedIrradiance;
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		indirectSpecular *= sheenEnergyComp;
		indirectDiffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectSpecular += indirectSpecular;
	reflectedLight.indirectDiffuse += indirectDiffuse;
}
#define RE_Direct				RE_Direct_Physical
#define RE_Direct_RectArea		RE_Direct_RectArea_Physical
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Physical
#define RE_IndirectSpecular		RE_IndirectSpecular_Physical
float computeSpecularOcclusion( const in float dotNV, const in float ambientOcclusion, const in float roughness ) {
	return saturate( pow( dotNV + ambientOcclusion, exp2( - 16.0 * roughness - 1.0 ) ) - 1.0 + ambientOcclusion );
}`,ll=`
vec3 geometryPosition = - vViewPosition;
vec3 geometryNormal = normal;
vec3 geometryViewDir = ( isOrthographic ) ? vec3( 0, 0, 1 ) : normalize( vViewPosition );
vec3 geometryClearcoatNormal = vec3( 0.0 );
#ifdef USE_CLEARCOAT
	geometryClearcoatNormal = clearcoatNormal;
#endif
#ifdef USE_IRIDESCENCE
	float dotNVi = saturate( dot( normal, geometryViewDir ) );
	if ( material.iridescenceThickness == 0.0 ) {
		material.iridescence = 0.0;
	} else {
		material.iridescence = saturate( material.iridescence );
	}
	if ( material.iridescence > 0.0 ) {
		material.iridescenceFresnelDielectric = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.specularColor );
		material.iridescenceFresnelMetallic = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.diffuseColor );
		material.iridescenceFresnel = mix( material.iridescenceFresnelDielectric, material.iridescenceFresnelMetallic, material.metalness );
		material.iridescenceF0 = Schlick_to_F0( material.iridescenceFresnel, 1.0, dotNVi );
	}
#endif
IncidentLight directLight;
#if ( NUM_POINT_LIGHTS > 0 ) && defined( RE_Direct )
	PointLight pointLight;
	#if defined( USE_SHADOWMAP ) && NUM_POINT_LIGHT_SHADOWS > 0
	PointLightShadow pointLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHTS; i ++ ) {
		pointLight = pointLights[ i ];
		getPointLightInfo( pointLight, geometryPosition, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_POINT_LIGHT_SHADOWS ) && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
		pointLightShadow = pointLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getPointShadow( pointShadowMap[ i ], pointLightShadow.shadowMapSize, pointLightShadow.shadowIntensity, pointLightShadow.shadowBias, pointLightShadow.shadowRadius, vPointShadowCoord[ i ], pointLightShadow.shadowCameraNear, pointLightShadow.shadowCameraFar ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_SPOT_LIGHTS > 0 ) && defined( RE_Direct )
	SpotLight spotLight;
	vec4 spotColor;
	vec3 spotLightCoord;
	bool inSpotLightMap;
	#if defined( USE_SHADOWMAP ) && NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHTS; i ++ ) {
		spotLight = spotLights[ i ];
		getSpotLightInfo( spotLight, geometryPosition, directLight );
		#if ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#define SPOT_LIGHT_MAP_INDEX UNROLLED_LOOP_INDEX
		#elif ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		#define SPOT_LIGHT_MAP_INDEX NUM_SPOT_LIGHT_MAPS
		#else
		#define SPOT_LIGHT_MAP_INDEX ( UNROLLED_LOOP_INDEX - NUM_SPOT_LIGHT_SHADOWS + NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#endif
		#if ( SPOT_LIGHT_MAP_INDEX < NUM_SPOT_LIGHT_MAPS )
			spotLightCoord = vSpotLightCoord[ i ].xyz / vSpotLightCoord[ i ].w;
			inSpotLightMap = all( lessThan( abs( spotLightCoord * 2. - 1. ), vec3( 1.0 ) ) );
			spotColor = texture2D( spotLightMap[ SPOT_LIGHT_MAP_INDEX ], spotLightCoord.xy );
			directLight.color = inSpotLightMap ? directLight.color * spotColor.rgb : directLight.color;
		#endif
		#undef SPOT_LIGHT_MAP_INDEX
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		spotLightShadow = spotLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( spotShadowMap[ i ], spotLightShadow.shadowMapSize, spotLightShadow.shadowIntensity, spotLightShadow.shadowBias, spotLightShadow.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_DIR_LIGHTS > 0 ) && defined( RE_Direct )
	DirectionalLight directionalLight;
	#if defined( USE_SHADOWMAP ) && NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHTS; i ++ ) {
		directionalLight = directionalLights[ i ];
		getDirectionalLightInfo( directionalLight, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_DIR_LIGHT_SHADOWS )
		directionalLightShadow = directionalLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( directionalShadowMap[ i ], directionalLightShadow.shadowMapSize, directionalLightShadow.shadowIntensity, directionalLightShadow.shadowBias, directionalLightShadow.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_RECT_AREA_LIGHTS > 0 ) && defined( RE_Direct_RectArea )
	RectAreaLight rectAreaLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_RECT_AREA_LIGHTS; i ++ ) {
		rectAreaLight = rectAreaLights[ i ];
		RE_Direct_RectArea( rectAreaLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if defined( RE_IndirectDiffuse )
	vec3 iblIrradiance = vec3( 0.0 );
	vec3 irradiance = getAmbientLightIrradiance( ambientLightColor );
	#if defined( USE_LIGHT_PROBES )
		irradiance += getLightProbeIrradiance( lightProbe, geometryNormal );
	#endif
	#if ( NUM_HEMI_LIGHTS > 0 )
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_HEMI_LIGHTS; i ++ ) {
			irradiance += getHemisphereLightIrradiance( hemisphereLights[ i ], geometryNormal );
		}
		#pragma unroll_loop_end
	#endif
	#ifdef USE_LIGHT_PROBES_GRID
		vec3 probeWorldPos = ( ( vec4( geometryPosition, 1.0 ) - viewMatrix[ 3 ] ) * viewMatrix ).xyz;
		vec3 probeWorldNormal = transformNormalByInverseViewMatrix( geometryNormal, viewMatrix );
		irradiance += getLightProbeGridIrradiance( probeWorldPos, probeWorldNormal );
	#endif
#endif
#if defined( RE_IndirectSpecular )
	vec3 radiance = vec3( 0.0 );
	vec3 clearcoatRadiance = vec3( 0.0 );
#endif`,ul=`#if defined( RE_IndirectDiffuse )
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		vec3 lightMapIrradiance = lightMapTexel.rgb * lightMapIntensity;
		irradiance += lightMapIrradiance;
	#endif
	#if defined( USE_ENVMAP ) && defined( ENVMAP_TYPE_CUBE_UV )
		#if defined( STANDARD ) || defined( LAMBERT ) || defined( PHONG )
			iblIrradiance += getIBLIrradiance( geometryNormal );
		#endif
	#endif
#endif
#if defined( USE_ENVMAP ) && defined( RE_IndirectSpecular )
	#ifdef USE_ANISOTROPY
		radiance += getIBLAnisotropyRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
	#else
		radiance += getIBLRadiance( geometryViewDir, geometryNormal, material.roughness );
	#endif
	#ifdef USE_CLEARCOAT
		clearcoatRadiance += getIBLRadiance( geometryViewDir, geometryClearcoatNormal, material.clearcoatRoughness );
	#endif
#endif`,hl=`#if defined( RE_IndirectDiffuse )
	#if defined( LAMBERT ) || defined( PHONG )
		irradiance += iblIrradiance;
	#endif
	RE_IndirectDiffuse( irradiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif
#if defined( RE_IndirectSpecular )
	RE_IndirectSpecular( radiance, iblIrradiance, clearcoatRadiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif`,fl=`#ifdef USE_LIGHT_PROBES_GRID
uniform highp sampler3D probesSH;
uniform vec3 probesMin;
uniform vec3 probesMax;
uniform vec3 probesResolution;
vec3 getLightProbeGridIrradiance( vec3 worldPos, vec3 worldNormal ) {
	vec3 res = probesResolution;
	vec3 gridRange = probesMax - probesMin;
	vec3 resMinusOne = res - 1.0;
	vec3 probeSpacing = gridRange / resMinusOne;
	vec3 samplePos = worldPos + worldNormal * probeSpacing * 0.5;
	vec3 uvw = clamp( ( samplePos - probesMin ) / gridRange, 0.0, 1.0 );
	uvw = uvw * resMinusOne / res + 0.5 / res;
	float nz          = res.z;
	float paddedSlices = nz + 2.0;
	float atlasDepth  = 7.0 * paddedSlices;
	float uvZBase     = uvw.z * nz + 1.0;
	vec4 s0 = texture( probesSH, vec3( uvw.xy, ( uvZBase                       ) / atlasDepth ) );
	vec4 s1 = texture( probesSH, vec3( uvw.xy, ( uvZBase +       paddedSlices   ) / atlasDepth ) );
	vec4 s2 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 2.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s3 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 3.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s4 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 4.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s5 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 5.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s6 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 6.0 * paddedSlices   ) / atlasDepth ) );
	vec3 c0 = s0.xyz;
	vec3 c1 = vec3( s0.w, s1.xy );
	vec3 c2 = vec3( s1.zw, s2.x );
	vec3 c3 = s2.yzw;
	vec3 c4 = s3.xyz;
	vec3 c5 = vec3( s3.w, s4.xy );
	vec3 c6 = vec3( s4.zw, s5.x );
	vec3 c7 = s5.yzw;
	vec3 c8 = s6.xyz;
	float x = worldNormal.x, y = worldNormal.y, z = worldNormal.z;
	vec3 result = c0 * 0.886227;
	result += c1 * 2.0 * 0.511664 * y;
	result += c2 * 2.0 * 0.511664 * z;
	result += c3 * 2.0 * 0.511664 * x;
	result += c4 * 2.0 * 0.429043 * x * y;
	result += c5 * 2.0 * 0.429043 * y * z;
	result += c6 * ( 0.743125 * z * z - 0.247708 );
	result += c7 * 2.0 * 0.429043 * x * z;
	result += c8 * 0.429043 * ( x * x - y * y );
	return max( result, vec3( 0.0 ) );
}
#endif`,dl=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	gl_FragDepth = vIsPerspective == 0.0 ? gl_FragCoord.z : log2( vFragDepth ) * logDepthBufFC * 0.5;
#endif`,pl=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	uniform float logDepthBufFC;
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,ml=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,gl=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	vFragDepth = 1.0 + gl_Position.w;
	vIsPerspective = float( isPerspectiveMatrix( projectionMatrix ) );
#endif`,xl=`#ifdef USE_MAP
	vec4 sampledDiffuseColor = texture2D( map, vMapUv );
	#ifdef DECODE_VIDEO_TEXTURE
		sampledDiffuseColor = sRGBTransferEOTF( sampledDiffuseColor );
	#endif
	diffuseColor *= sampledDiffuseColor;
#endif`,_l=`#ifdef USE_MAP
	uniform sampler2D map;
#endif`,yl=`#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
	#if defined( USE_POINTS_UV )
		vec2 uv = vUv;
	#else
		vec2 uv = ( uvTransform * vec3( gl_PointCoord.x, 1.0 - gl_PointCoord.y, 1 ) ).xy;
	#endif
#endif
#ifdef USE_MAP
	diffuseColor *= texture2D( map, uv );
#endif
#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, uv ).g;
#endif`,vl=`#if defined( USE_POINTS_UV )
	varying vec2 vUv;
#else
	#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
		uniform mat3 uvTransform;
	#endif
#endif
#ifdef USE_MAP
	uniform sampler2D map;
#endif
#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,Ml=`float metalnessFactor = metalness;
#ifdef USE_METALNESSMAP
	vec4 texelMetalness = texture2D( metalnessMap, vMetalnessMapUv );
	metalnessFactor *= texelMetalness.b;
#endif`,bl=`#ifdef USE_METALNESSMAP
	uniform sampler2D metalnessMap;
#endif`,Sl=`#ifdef USE_INSTANCING_MORPH
	float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	float morphTargetBaseInfluence = texelFetch( morphTexture, ivec2( 0, gl_InstanceID ), 0 ).r;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		morphTargetInfluences[i] =  texelFetch( morphTexture, ivec2( i + 1, gl_InstanceID ), 0 ).r;
	}
#endif`,Al=`#if defined( USE_MORPHCOLORS )
	vColor *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		#if defined( USE_COLOR_ALPHA )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ) * morphTargetInfluences[ i ];
		#elif defined( USE_COLOR )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ).rgb * morphTargetInfluences[ i ];
		#endif
	}
#endif`,wl=`#ifdef USE_MORPHNORMALS
	objectNormal *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) objectNormal += getMorph( gl_VertexID, i, 1 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,Tl=`#ifdef USE_MORPHTARGETS
	#ifndef USE_INSTANCING_MORPH
		uniform float morphTargetBaseInfluence;
		uniform float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	#endif
	uniform sampler2DArray morphTargetsTexture;
	uniform ivec2 morphTargetsTextureSize;
	vec4 getMorph( const in int vertexIndex, const in int morphTargetIndex, const in int offset ) {
		int texelIndex = vertexIndex * MORPHTARGETS_TEXTURE_STRIDE + offset;
		int y = texelIndex / morphTargetsTextureSize.x;
		int x = texelIndex - y * morphTargetsTextureSize.x;
		ivec3 morphUV = ivec3( x, y, morphTargetIndex );
		return texelFetch( morphTargetsTexture, morphUV, 0 );
	}
#endif`,El=`#ifdef USE_MORPHTARGETS
	transformed *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) transformed += getMorph( gl_VertexID, i, 0 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,Cl=`float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;
#ifdef FLAT_SHADED
	vec3 fdx = dFdx( vViewPosition );
	vec3 fdy = dFdy( vViewPosition );
	vec3 normal = normalize( cross( fdx, fdy ) );
#else
	vec3 normal = normalize( vNormal );
	#ifdef DOUBLE_SIDED
		normal *= faceDirection;
	#endif
#endif
#if defined( USE_NORMALMAP_TANGENTSPACE ) || defined( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY )
	#ifdef USE_TANGENT
		mat3 tbn = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn = getTangentFrame( - vViewPosition, normal,
		#if defined( USE_NORMALMAP )
			vNormalMapUv
		#elif defined( USE_CLEARCOAT_NORMALMAP )
			vClearcoatNormalMapUv
		#else
			vUv
		#endif
		);
	#endif
	#ifdef DOUBLE_SIDED
		tbn[0] *= faceDirection;
		tbn[1] *= faceDirection;
	#endif
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	#ifdef USE_TANGENT
		mat3 tbn2 = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn2 = getTangentFrame( - vViewPosition, normal, vClearcoatNormalMapUv );
	#endif
	#ifdef DOUBLE_SIDED
		tbn2[0] *= faceDirection;
		tbn2[1] *= faceDirection;
	#endif
#endif
vec3 nonPerturbedNormal = normal;`,Rl=`#ifdef USE_NORMALMAP_OBJECTSPACE
	normal = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#ifdef FLIP_SIDED
		normal = - normal;
	#endif
	#ifdef DOUBLE_SIDED
		normal = normal * faceDirection;
	#endif
	normal = normalize( normalMatrix * normal );
#elif defined( USE_NORMALMAP_TANGENTSPACE )
	vec3 mapN = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#if defined( USE_PACKED_NORMALMAP )
		mapN = vec3( mapN.xy, sqrt( saturate( 1.0 - dot( mapN.xy, mapN.xy ) ) ) );
	#endif
	mapN.xy *= normalScale;
	normal = normalize( tbn * mapN );
#elif defined( USE_BUMPMAP )
	normal = perturbNormalArb( - vViewPosition, normal, dHdxy_fwd(), faceDirection );
#endif`,Il=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,Pl=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,Ll=`#ifndef FLAT_SHADED
	vNormal = normalize( transformedNormal );
	#ifdef USE_TANGENT
		vTangent = normalize( transformedTangent );
		vBitangent = normalize( cross( vNormal, vTangent ) * tangent.w );
		#ifdef FLIP_SIDED
			vBitangent = - vBitangent;
		#endif
	#endif
#endif`,Nl=`#ifdef USE_NORMALMAP
	uniform sampler2D normalMap;
	uniform vec2 normalScale;
#endif
#ifdef USE_NORMALMAP_OBJECTSPACE
	uniform mat3 normalMatrix;
#endif
#if ! defined ( USE_TANGENT ) && ( defined ( USE_NORMALMAP_TANGENTSPACE ) || defined ( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY ) )
	mat3 getTangentFrame( vec3 eye_pos, vec3 surf_norm, vec2 uv ) {
		vec3 q0 = dFdx( eye_pos.xyz );
		vec3 q1 = dFdy( eye_pos.xyz );
		vec2 st0 = dFdx( uv.st );
		vec2 st1 = dFdy( uv.st );
		vec3 N = surf_norm;
		vec3 q1perp = cross( q1, N );
		vec3 q0perp = cross( N, q0 );
		vec3 T = q1perp * st0.x + q0perp * st1.x;
		vec3 B = q1perp * st0.y + q0perp * st1.y;
		float det = max( dot( T, T ), dot( B, B ) );
		float scale = ( det == 0.0 ) ? 0.0 : inversesqrt( det );
		return mat3( T * scale, B * scale, N );
	}
#endif`,Dl=`#ifdef USE_CLEARCOAT
	vec3 clearcoatNormal = nonPerturbedNormal;
#endif`,Ul=`#ifdef USE_CLEARCOAT_NORMALMAP
	vec3 clearcoatMapN = texture2D( clearcoatNormalMap, vClearcoatNormalMapUv ).xyz * 2.0 - 1.0;
	clearcoatMapN.xy *= clearcoatNormalScale;
	clearcoatNormal = normalize( tbn2 * clearcoatMapN );
#endif`,Fl=`#ifdef USE_CLEARCOATMAP
	uniform sampler2D clearcoatMap;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform sampler2D clearcoatNormalMap;
	uniform vec2 clearcoatNormalScale;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform sampler2D clearcoatRoughnessMap;
#endif`,Ol=`#ifdef USE_IRIDESCENCEMAP
	uniform sampler2D iridescenceMap;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform sampler2D iridescenceThicknessMap;
#endif`,Bl=`#ifdef OPAQUE
diffuseColor.a = 1.0;
#endif
#ifdef USE_TRANSMISSION
diffuseColor.a *= material.transmissionAlpha;
#endif
gl_FragColor = vec4( outgoingLight, diffuseColor.a );`,zl=`vec3 packNormalToRGB( const in vec3 normal ) {
	return normalize( normal ) * 0.5 + 0.5;
}
vec3 unpackRGBToNormal( const in vec3 rgb ) {
	return 2.0 * rgb.xyz - 1.0;
}
const float PackUpscale = 256. / 255.;const float UnpackDownscale = 255. / 256.;const float ShiftRight8 = 1. / 256.;
const float Inv255 = 1. / 255.;
const vec4 PackFactors = vec4( 1.0, 256.0, 256.0 * 256.0, 256.0 * 256.0 * 256.0 );
const vec2 UnpackFactors2 = vec2( UnpackDownscale, 1.0 / PackFactors.g );
const vec3 UnpackFactors3 = vec3( UnpackDownscale / PackFactors.rg, 1.0 / PackFactors.b );
const vec4 UnpackFactors4 = vec4( UnpackDownscale / PackFactors.rgb, 1.0 / PackFactors.a );
vec4 packDepthToRGBA( const in float v ) {
	if( v <= 0.0 )
		return vec4( 0., 0., 0., 0. );
	if( v >= 1.0 )
		return vec4( 1., 1., 1., 1. );
	float vuf;
	float af = modf( v * PackFactors.a, vuf );
	float bf = modf( vuf * ShiftRight8, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec4( vuf * Inv255, gf * PackUpscale, bf * PackUpscale, af );
}
vec3 packDepthToRGB( const in float v ) {
	if( v <= 0.0 )
		return vec3( 0., 0., 0. );
	if( v >= 1.0 )
		return vec3( 1., 1., 1. );
	float vuf;
	float bf = modf( v * PackFactors.b, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec3( vuf * Inv255, gf * PackUpscale, bf );
}
vec2 packDepthToRG( const in float v ) {
	if( v <= 0.0 )
		return vec2( 0., 0. );
	if( v >= 1.0 )
		return vec2( 1., 1. );
	float vuf;
	float gf = modf( v * 256., vuf );
	return vec2( vuf * Inv255, gf );
}
float unpackRGBAToDepth( const in vec4 v ) {
	return dot( v, UnpackFactors4 );
}
float unpackRGBToDepth( const in vec3 v ) {
	return dot( v, UnpackFactors3 );
}
float unpackRGToDepth( const in vec2 v ) {
	return v.r * UnpackFactors2.r + v.g * UnpackFactors2.g;
}
vec4 pack2HalfToRGBA( const in vec2 v ) {
	vec4 r = vec4( v.x, fract( v.x * 255.0 ), v.y, fract( v.y * 255.0 ) );
	return vec4( r.x - r.y / 255.0, r.y, r.z - r.w / 255.0, r.w );
}
vec2 unpackRGBATo2Half( const in vec4 v ) {
	return vec2( v.x + ( v.y / 255.0 ), v.z + ( v.w / 255.0 ) );
}
float viewZToOrthographicDepth( const in float viewZ, const in float near, const in float far ) {
	return ( viewZ + near ) / ( near - far );
}
float orthographicDepthToViewZ( const in float depth, const in float near, const in float far ) {
	#ifdef USE_REVERSED_DEPTH_BUFFER
	
		return depth * ( far - near ) - far;
	#else
		return depth * ( near - far ) - near;
	#endif
}
float viewZToPerspectiveDepth( const in float viewZ, const in float near, const in float far ) {
	return ( ( near + viewZ ) * far ) / ( ( far - near ) * viewZ );
}
float perspectiveDepthToViewZ( const in float depth, const in float near, const in float far ) {
	
	#ifdef USE_REVERSED_DEPTH_BUFFER
		return ( near * far ) / ( ( near - far ) * depth - near );
	#else
		return ( near * far ) / ( ( far - near ) * depth - far );
	#endif
}`,kl=`#ifdef PREMULTIPLIED_ALPHA
	gl_FragColor.rgb *= gl_FragColor.a;
#endif`,Vl=`vec4 mvPosition = vec4( transformed, 1.0 );
#ifdef USE_BATCHING
	mvPosition = batchingMatrix * mvPosition;
#endif
#ifdef USE_INSTANCING
	mvPosition = instanceMatrix * mvPosition;
#endif
mvPosition = modelViewMatrix * mvPosition;
gl_Position = projectionMatrix * mvPosition;`,Gl=`#ifdef DITHERING
	gl_FragColor.rgb = dithering( gl_FragColor.rgb );
#endif`,Hl=`#ifdef DITHERING
	vec3 dithering( vec3 color ) {
		float grid_position = rand( gl_FragCoord.xy );
		vec3 dither_shift_RGB = vec3( 0.25 / 255.0, -0.25 / 255.0, 0.25 / 255.0 );
		dither_shift_RGB = mix( 2.0 * dither_shift_RGB, -2.0 * dither_shift_RGB, grid_position );
		return color + dither_shift_RGB;
	}
#endif`,Wl=`float roughnessFactor = roughness;
#ifdef USE_ROUGHNESSMAP
	vec4 texelRoughness = texture2D( roughnessMap, vRoughnessMapUv );
	roughnessFactor *= texelRoughness.g;
#endif`,Xl=`#ifdef USE_ROUGHNESSMAP
	uniform sampler2D roughnessMap;
#endif`,ql=`#if NUM_SPOT_LIGHT_COORDS > 0
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#if NUM_SPOT_LIGHT_MAPS > 0
	uniform sampler2D spotLightMap[ NUM_SPOT_LIGHT_MAPS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#else
			uniform sampler2D directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#endif
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#else
			uniform sampler2D spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#endif
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform samplerCubeShadow pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#elif defined( SHADOWMAP_TYPE_BASIC )
			uniform samplerCube pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#endif
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float interleavedGradientNoise( vec2 position ) {
			return fract( 52.9829189 * fract( dot( position, vec2( 0.06711056, 0.00583715 ) ) ) );
		}
		vec2 vogelDiskSample( int sampleIndex, int samplesCount, float phi ) {
			const float goldenAngle = 2.399963229728653;
			float r = sqrt( ( float( sampleIndex ) + 0.5 ) / float( samplesCount ) );
			float theta = float( sampleIndex ) * goldenAngle + phi;
			return vec2( cos( theta ), sin( theta ) ) * r;
		}
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float getShadow( sampler2DShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			shadowCoord.z += shadowBias;
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 texelSize = vec2( 1.0 ) / shadowMapSize;
				float radius = shadowRadius * texelSize.x;
				float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
				shadow = (
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 0, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 1, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 2, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 3, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 4, 5, phi ) * radius, shadowCoord.z ) )
				) * 0.2;
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#elif defined( SHADOWMAP_TYPE_VSM )
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 distribution = texture2D( shadowMap, shadowCoord.xy ).rg;
				float mean = distribution.x;
				float variance = distribution.y * distribution.y;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					float hard_shadow = step( mean, shadowCoord.z );
				#else
					float hard_shadow = step( shadowCoord.z, mean );
				#endif
				
				if ( hard_shadow == 1.0 ) {
					shadow = 1.0;
				} else {
					variance = max( variance, 0.0000001 );
					float d = shadowCoord.z - mean;
					float p_max = variance / ( variance + d * d );
					p_max = clamp( ( p_max - 0.3 ) / 0.65, 0.0, 1.0 );
					shadow = max( hard_shadow, p_max );
				}
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#else
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				float depth = texture2D( shadowMap, shadowCoord.xy ).r;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					shadow = step( depth, shadowCoord.z );
				#else
					shadow = step( shadowCoord.z, depth );
				#endif
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
	#if defined( SHADOWMAP_TYPE_PCF )
	float getPointShadow( samplerCubeShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 bd3D = normalize( lightToPosition );
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			#ifdef USE_REVERSED_DEPTH_BUFFER
				float dp = ( shadowCameraNear * ( shadowCameraFar - viewSpaceZ ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp -= shadowBias;
			#else
				float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp += shadowBias;
			#endif
			float texelSize = shadowRadius / shadowMapSize.x;
			vec3 absDir = abs( bd3D );
			vec3 tangent = absDir.x > absDir.z ? vec3( 0.0, 1.0, 0.0 ) : vec3( 1.0, 0.0, 0.0 );
			tangent = normalize( cross( bd3D, tangent ) );
			vec3 bitangent = cross( bd3D, tangent );
			float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
			vec2 sample0 = vogelDiskSample( 0, 5, phi );
			vec2 sample1 = vogelDiskSample( 1, 5, phi );
			vec2 sample2 = vogelDiskSample( 2, 5, phi );
			vec2 sample3 = vogelDiskSample( 3, 5, phi );
			vec2 sample4 = vogelDiskSample( 4, 5, phi );
			shadow = (
				texture( shadowMap, vec4( bd3D + ( tangent * sample0.x + bitangent * sample0.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample1.x + bitangent * sample1.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample2.x + bitangent * sample2.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample3.x + bitangent * sample3.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample4.x + bitangent * sample4.y ) * texelSize, dp ) )
			) * 0.2;
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#elif defined( SHADOWMAP_TYPE_BASIC )
	float getPointShadow( samplerCube shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
			dp += shadowBias;
			vec3 bd3D = normalize( lightToPosition );
			float depth = textureCube( shadowMap, bd3D ).r;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				depth = 1.0 - depth;
			#endif
			shadow = step( dp, depth );
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#endif
	#endif
#endif`,$l=`#if NUM_SPOT_LIGHT_COORDS > 0
	uniform mat4 spotLightMatrix[ NUM_SPOT_LIGHT_COORDS ];
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
		uniform mat4 directionalShadowMatrix[ NUM_DIR_LIGHT_SHADOWS ];
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		uniform mat4 pointShadowMatrix[ NUM_POINT_LIGHT_SHADOWS ];
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
#endif`,Yl=`#if ( defined( USE_SHADOWMAP ) && ( NUM_DIR_LIGHT_SHADOWS > 0 || NUM_POINT_LIGHT_SHADOWS > 0 ) ) || ( NUM_SPOT_LIGHT_COORDS > 0 )
	#ifdef HAS_NORMAL
		vec3 shadowWorldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
	#else
		vec3 shadowWorldNormal = vec3( 0.0 );
	#endif
	vec4 shadowWorldPosition;
#endif
#if defined( USE_SHADOWMAP )
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * directionalLightShadows[ i ].shadowNormalBias, 0 );
			vDirectionalShadowCoord[ i ] = directionalShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * pointLightShadows[ i ].shadowNormalBias, 0 );
			vPointShadowCoord[ i ] = pointShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
#endif
#if NUM_SPOT_LIGHT_COORDS > 0
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_COORDS; i ++ ) {
		shadowWorldPosition = worldPosition;
		#if ( defined( USE_SHADOWMAP ) && UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
			shadowWorldPosition.xyz += shadowWorldNormal * spotLightShadows[ i ].shadowNormalBias;
		#endif
		vSpotLightCoord[ i ] = spotLightMatrix[ i ] * shadowWorldPosition;
	}
	#pragma unroll_loop_end
#endif`,Zl=`float getShadowMask() {
	float shadow = 1.0;
	#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
		directionalLight = directionalLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( directionalShadowMap[ i ], directionalLight.shadowMapSize, directionalLight.shadowIntensity, directionalLight.shadowBias, directionalLight.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_SHADOWS; i ++ ) {
		spotLight = spotLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( spotShadowMap[ i ], spotLight.shadowMapSize, spotLight.shadowIntensity, spotLight.shadowBias, spotLight.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0 && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
	PointLightShadow pointLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
		pointLight = pointLightShadows[ i ];
		shadow *= receiveShadow ? getPointShadow( pointShadowMap[ i ], pointLight.shadowMapSize, pointLight.shadowIntensity, pointLight.shadowBias, pointLight.shadowRadius, vPointShadowCoord[ i ], pointLight.shadowCameraNear, pointLight.shadowCameraFar ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#endif
	return shadow;
}`,Jl=`#ifdef USE_SKINNING
	mat4 boneMatX = getBoneMatrix( skinIndex.x );
	mat4 boneMatY = getBoneMatrix( skinIndex.y );
	mat4 boneMatZ = getBoneMatrix( skinIndex.z );
	mat4 boneMatW = getBoneMatrix( skinIndex.w );
#endif`,Kl=`#ifdef USE_SKINNING
	uniform mat4 bindMatrix;
	uniform mat4 bindMatrixInverse;
	uniform highp sampler2D boneTexture;
	mat4 getBoneMatrix( const in float i ) {
		int size = textureSize( boneTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( boneTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( boneTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( boneTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( boneTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
#endif`,jl=`#ifdef USE_SKINNING
	vec4 skinVertex = bindMatrix * vec4( transformed, 1.0 );
	vec4 skinned = vec4( 0.0 );
	skinned += boneMatX * skinVertex * skinWeight.x;
	skinned += boneMatY * skinVertex * skinWeight.y;
	skinned += boneMatZ * skinVertex * skinWeight.z;
	skinned += boneMatW * skinVertex * skinWeight.w;
	transformed = ( bindMatrixInverse * skinned ).xyz;
#endif`,Ql=`#ifdef USE_SKINNING
	mat4 skinMatrix = mat4( 0.0 );
	skinMatrix += skinWeight.x * boneMatX;
	skinMatrix += skinWeight.y * boneMatY;
	skinMatrix += skinWeight.z * boneMatZ;
	skinMatrix += skinWeight.w * boneMatW;
	skinMatrix = bindMatrixInverse * skinMatrix * bindMatrix;
	objectNormal = vec4( skinMatrix * vec4( objectNormal, 0.0 ) ).xyz;
	#ifdef USE_TANGENT
		objectTangent = vec4( skinMatrix * vec4( objectTangent, 0.0 ) ).xyz;
	#endif
#endif`,tu=`float specularStrength;
#ifdef USE_SPECULARMAP
	vec4 texelSpecular = texture2D( specularMap, vSpecularMapUv );
	specularStrength = texelSpecular.r;
#else
	specularStrength = 1.0;
#endif`,eu=`#ifdef USE_SPECULARMAP
	uniform sampler2D specularMap;
#endif`,nu=`#if defined( TONE_MAPPING )
	gl_FragColor.rgb = toneMapping( gl_FragColor.rgb );
#endif`,iu=`#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
uniform float toneMappingExposure;
vec3 LinearToneMapping( vec3 color ) {
	return saturate( toneMappingExposure * color );
}
vec3 ReinhardToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	return saturate( color / ( vec3( 1.0 ) + color ) );
}
vec3 CineonToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	color = max( vec3( 0.0 ), color - 0.004 );
	return pow( ( color * ( 6.2 * color + 0.5 ) ) / ( color * ( 6.2 * color + 1.7 ) + 0.06 ), vec3( 2.2 ) );
}
vec3 RRTAndODTFit( vec3 v ) {
	vec3 a = v * ( v + 0.0245786 ) - 0.000090537;
	vec3 b = v * ( 0.983729 * v + 0.4329510 ) + 0.238081;
	return a / b;
}
vec3 ACESFilmicToneMapping( vec3 color ) {
	const mat3 ACESInputMat = mat3(
		vec3( 0.59719, 0.07600, 0.02840 ),		vec3( 0.35458, 0.90834, 0.13383 ),
		vec3( 0.04823, 0.01566, 0.83777 )
	);
	const mat3 ACESOutputMat = mat3(
		vec3(  1.60475, -0.10208, -0.00327 ),		vec3( -0.53108,  1.10813, -0.07276 ),
		vec3( -0.07367, -0.00605,  1.07602 )
	);
	color *= toneMappingExposure / 0.6;
	color = ACESInputMat * color;
	color = RRTAndODTFit( color );
	color = ACESOutputMat * color;
	return saturate( color );
}
const mat3 LINEAR_REC2020_TO_LINEAR_SRGB = mat3(
	vec3( 1.6605, - 0.1246, - 0.0182 ),
	vec3( - 0.5876, 1.1329, - 0.1006 ),
	vec3( - 0.0728, - 0.0083, 1.1187 )
);
const mat3 LINEAR_SRGB_TO_LINEAR_REC2020 = mat3(
	vec3( 0.6274, 0.0691, 0.0164 ),
	vec3( 0.3293, 0.9195, 0.0880 ),
	vec3( 0.0433, 0.0113, 0.8956 )
);
vec3 agxDefaultContrastApprox( vec3 x ) {
	vec3 x2 = x * x;
	vec3 x4 = x2 * x2;
	return + 15.5 * x4 * x2
		- 40.14 * x4 * x
		+ 31.96 * x4
		- 6.868 * x2 * x
		+ 0.4298 * x2
		+ 0.1191 * x
		- 0.00232;
}
vec3 AgXToneMapping( vec3 color ) {
	const mat3 AgXInsetMatrix = mat3(
		vec3( 0.856627153315983, 0.137318972929847, 0.11189821299995 ),
		vec3( 0.0951212405381588, 0.761241990602591, 0.0767994186031903 ),
		vec3( 0.0482516061458583, 0.101439036467562, 0.811302368396859 )
	);
	const mat3 AgXOutsetMatrix = mat3(
		vec3( 1.1271005818144368, - 0.1413297634984383, - 0.14132976349843826 ),
		vec3( - 0.11060664309660323, 1.157823702216272, - 0.11060664309660294 ),
		vec3( - 0.016493938717834573, - 0.016493938717834257, 1.2519364065950405 )
	);
	const float AgxMinEv = - 12.47393;	const float AgxMaxEv = 4.026069;
	color *= toneMappingExposure;
	color = LINEAR_SRGB_TO_LINEAR_REC2020 * color;
	color = AgXInsetMatrix * color;
	color = max( color, 1e-10 );	color = log2( color );
	color = ( color - AgxMinEv ) / ( AgxMaxEv - AgxMinEv );
	color = clamp( color, 0.0, 1.0 );
	color = agxDefaultContrastApprox( color );
	color = AgXOutsetMatrix * color;
	color = pow( max( vec3( 0.0 ), color ), vec3( 2.2 ) );
	color = LINEAR_REC2020_TO_LINEAR_SRGB * color;
	color = clamp( color, 0.0, 1.0 );
	return color;
}
vec3 NeutralToneMapping( vec3 color ) {
	const float StartCompression = 0.8 - 0.04;
	const float Desaturation = 0.15;
	color *= toneMappingExposure;
	float x = min( color.r, min( color.g, color.b ) );
	float offset = x < 0.08 ? x - 6.25 * x * x : 0.04;
	color -= offset;
	float peak = max( color.r, max( color.g, color.b ) );
	if ( peak < StartCompression ) return color;
	float d = 1. - StartCompression;
	float newPeak = 1. - d * d / ( peak + d - StartCompression );
	color *= newPeak / peak;
	float g = 1. - 1. / ( Desaturation * ( peak - newPeak ) + 1. );
	return mix( color, vec3( newPeak ), g );
}
vec3 CustomToneMapping( vec3 color ) { return color; }`,su=`#ifdef USE_TRANSMISSION
	material.transmission = transmission;
	material.transmissionAlpha = 1.0;
	material.thickness = thickness;
	material.attenuationDistance = attenuationDistance;
	material.attenuationColor = attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		material.transmission *= texture2D( transmissionMap, vTransmissionMapUv ).r;
	#endif
	#ifdef USE_THICKNESSMAP
		material.thickness *= texture2D( thicknessMap, vThicknessMapUv ).g;
	#endif
	vec3 pos = vWorldPosition;
	vec3 v = normalize( cameraPosition - pos );
	vec3 n = transformNormalByInverseViewMatrix( normal, viewMatrix );
	vec4 transmitted = getIBLVolumeRefraction(
		n, v, material.roughness, material.diffuseContribution, material.specularColorBlended, material.specularF90,
		pos, modelMatrix, viewMatrix, projectionMatrix, material.dispersion, material.ior, material.thickness,
		material.attenuationColor, material.attenuationDistance );
	material.transmissionAlpha = mix( material.transmissionAlpha, transmitted.a, material.transmission );
	totalDiffuse = mix( totalDiffuse, transmitted.rgb, material.transmission );
#endif`,ru=`#ifdef USE_TRANSMISSION
	uniform float transmission;
	uniform float thickness;
	uniform float attenuationDistance;
	uniform vec3 attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		uniform sampler2D transmissionMap;
	#endif
	#ifdef USE_THICKNESSMAP
		uniform sampler2D thicknessMap;
	#endif
	uniform vec2 transmissionSamplerSize;
	uniform sampler2D transmissionSamplerMap;
	uniform mat4 modelMatrix;
	uniform mat4 projectionMatrix;
	varying vec3 vWorldPosition;
	float w0( float a ) {
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - a + 3.0 ) - 3.0 ) + 1.0 );
	}
	float w1( float a ) {
		return ( 1.0 / 6.0 ) * ( a *  a * ( 3.0 * a - 6.0 ) + 4.0 );
	}
	float w2( float a ){
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - 3.0 * a + 3.0 ) + 3.0 ) + 1.0 );
	}
	float w3( float a ) {
		return ( 1.0 / 6.0 ) * ( a * a * a );
	}
	float g0( float a ) {
		return w0( a ) + w1( a );
	}
	float g1( float a ) {
		return w2( a ) + w3( a );
	}
	float h0( float a ) {
		return - 1.0 + w1( a ) / ( w0( a ) + w1( a ) );
	}
	float h1( float a ) {
		return 1.0 + w3( a ) / ( w2( a ) + w3( a ) );
	}
	vec4 bicubic( sampler2D tex, vec2 uv, vec4 texelSize, float lod ) {
		uv = uv * texelSize.zw + 0.5;
		vec2 iuv = floor( uv );
		vec2 fuv = fract( uv );
		float g0x = g0( fuv.x );
		float g1x = g1( fuv.x );
		float h0x = h0( fuv.x );
		float h1x = h1( fuv.x );
		float h0y = h0( fuv.y );
		float h1y = h1( fuv.y );
		vec2 p0 = ( vec2( iuv.x + h0x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p1 = ( vec2( iuv.x + h1x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p2 = ( vec2( iuv.x + h0x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		vec2 p3 = ( vec2( iuv.x + h1x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		return g0( fuv.y ) * ( g0x * textureLod( tex, p0, lod ) + g1x * textureLod( tex, p1, lod ) ) +
			g1( fuv.y ) * ( g0x * textureLod( tex, p2, lod ) + g1x * textureLod( tex, p3, lod ) );
	}
	vec4 textureBicubic( sampler2D sampler, vec2 uv, float lod ) {
		vec2 fLodSize = vec2( textureSize( sampler, int( lod ) ) );
		vec2 cLodSize = vec2( textureSize( sampler, int( lod + 1.0 ) ) );
		vec2 fLodSizeInv = 1.0 / fLodSize;
		vec2 cLodSizeInv = 1.0 / cLodSize;
		vec4 fSample = bicubic( sampler, uv, vec4( fLodSizeInv, fLodSize ), floor( lod ) );
		vec4 cSample = bicubic( sampler, uv, vec4( cLodSizeInv, cLodSize ), ceil( lod ) );
		return mix( fSample, cSample, fract( lod ) );
	}
	vec3 getVolumeTransmissionRay( const in vec3 n, const in vec3 v, const in float thickness, const in float ior, const in mat4 modelMatrix ) {
		vec3 refractionVector = refract( - v, normalize( n ), 1.0 / ior );
		vec3 modelScale;
		modelScale.x = length( vec3( modelMatrix[ 0 ].xyz ) );
		modelScale.y = length( vec3( modelMatrix[ 1 ].xyz ) );
		modelScale.z = length( vec3( modelMatrix[ 2 ].xyz ) );
		return normalize( refractionVector ) * thickness * modelScale;
	}
	float applyIorToRoughness( const in float roughness, const in float ior ) {
		return roughness * clamp( ior * 2.0 - 2.0, 0.0, 1.0 );
	}
	vec4 getTransmissionSample( const in vec2 fragCoord, const in float roughness, const in float ior ) {
		float lod = log2( transmissionSamplerSize.x ) * applyIorToRoughness( roughness, ior );
		return textureBicubic( transmissionSamplerMap, fragCoord.xy, lod );
	}
	vec3 volumeAttenuation( const in float transmissionDistance, const in vec3 attenuationColor, const in float attenuationDistance ) {
		if ( isinf( attenuationDistance ) ) {
			return vec3( 1.0 );
		} else {
			vec3 attenuationCoefficient = -log( attenuationColor ) / attenuationDistance;
			vec3 transmittance = exp( - attenuationCoefficient * transmissionDistance );			return transmittance;
		}
	}
	vec4 getIBLVolumeRefraction( const in vec3 n, const in vec3 v, const in float roughness, const in vec3 diffuseColor,
		const in vec3 specularColor, const in float specularF90, const in vec3 position, const in mat4 modelMatrix,
		const in mat4 viewMatrix, const in mat4 projMatrix, const in float dispersion, const in float ior, const in float thickness,
		const in vec3 attenuationColor, const in float attenuationDistance ) {
		vec4 transmittedLight;
		vec3 transmittance;
		#ifdef USE_DISPERSION
			float halfSpread = ( ior - 1.0 ) * 0.025 * dispersion;
			vec3 iors = vec3( ior - halfSpread, ior, ior + halfSpread );
			for ( int i = 0; i < 3; i ++ ) {
				vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, iors[ i ], modelMatrix );
				vec3 refractedRayExit = position + transmissionRay;
				vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
				vec2 refractionCoords = ndcPos.xy / ndcPos.w;
				refractionCoords += 1.0;
				refractionCoords /= 2.0;
				vec4 transmissionSample = getTransmissionSample( refractionCoords, roughness, iors[ i ] );
				transmittedLight[ i ] = transmissionSample[ i ];
				transmittedLight.a += transmissionSample.a;
				transmittance[ i ] = diffuseColor[ i ] * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance )[ i ];
			}
			transmittedLight.a /= 3.0;
		#else
			vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, ior, modelMatrix );
			vec3 refractedRayExit = position + transmissionRay;
			vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
			vec2 refractionCoords = ndcPos.xy / ndcPos.w;
			refractionCoords += 1.0;
			refractionCoords /= 2.0;
			transmittedLight = getTransmissionSample( refractionCoords, roughness, ior );
			transmittance = diffuseColor * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance );
		#endif
		vec3 attenuatedColor = transmittance * transmittedLight.rgb;
		vec3 F = EnvironmentBRDF( n, v, specularColor, specularF90, roughness );
		float transmittanceFactor = ( transmittance.r + transmittance.g + transmittance.b ) / 3.0;
		return vec4( ( 1.0 - F ) * attenuatedColor, 1.0 - ( 1.0 - transmittedLight.a ) * transmittanceFactor );
	}
#endif`,ou=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_SPECULARMAP
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,au=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	uniform mat3 mapTransform;
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	uniform mat3 alphaMapTransform;
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	uniform mat3 lightMapTransform;
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	uniform mat3 aoMapTransform;
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	uniform mat3 bumpMapTransform;
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	uniform mat3 normalMapTransform;
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_DISPLACEMENTMAP
	uniform mat3 displacementMapTransform;
	varying vec2 vDisplacementMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	uniform mat3 emissiveMapTransform;
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	uniform mat3 metalnessMapTransform;
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	uniform mat3 roughnessMapTransform;
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	uniform mat3 anisotropyMapTransform;
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	uniform mat3 clearcoatMapTransform;
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform mat3 clearcoatNormalMapTransform;
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform mat3 clearcoatRoughnessMapTransform;
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	uniform mat3 sheenColorMapTransform;
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	uniform mat3 sheenRoughnessMapTransform;
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	uniform mat3 iridescenceMapTransform;
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform mat3 iridescenceThicknessMapTransform;
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SPECULARMAP
	uniform mat3 specularMapTransform;
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	uniform mat3 specularColorMapTransform;
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	uniform mat3 specularIntensityMapTransform;
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,cu=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	vUv = vec3( uv, 1 ).xy;
#endif
#ifdef USE_MAP
	vMapUv = ( mapTransform * vec3( MAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ALPHAMAP
	vAlphaMapUv = ( alphaMapTransform * vec3( ALPHAMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_LIGHTMAP
	vLightMapUv = ( lightMapTransform * vec3( LIGHTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_AOMAP
	vAoMapUv = ( aoMapTransform * vec3( AOMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_BUMPMAP
	vBumpMapUv = ( bumpMapTransform * vec3( BUMPMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_NORMALMAP
	vNormalMapUv = ( normalMapTransform * vec3( NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_DISPLACEMENTMAP
	vDisplacementMapUv = ( displacementMapTransform * vec3( DISPLACEMENTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_EMISSIVEMAP
	vEmissiveMapUv = ( emissiveMapTransform * vec3( EMISSIVEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_METALNESSMAP
	vMetalnessMapUv = ( metalnessMapTransform * vec3( METALNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ROUGHNESSMAP
	vRoughnessMapUv = ( roughnessMapTransform * vec3( ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ANISOTROPYMAP
	vAnisotropyMapUv = ( anisotropyMapTransform * vec3( ANISOTROPYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOATMAP
	vClearcoatMapUv = ( clearcoatMapTransform * vec3( CLEARCOATMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	vClearcoatNormalMapUv = ( clearcoatNormalMapTransform * vec3( CLEARCOAT_NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	vClearcoatRoughnessMapUv = ( clearcoatRoughnessMapTransform * vec3( CLEARCOAT_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCEMAP
	vIridescenceMapUv = ( iridescenceMapTransform * vec3( IRIDESCENCEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	vIridescenceThicknessMapUv = ( iridescenceThicknessMapTransform * vec3( IRIDESCENCE_THICKNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_COLORMAP
	vSheenColorMapUv = ( sheenColorMapTransform * vec3( SHEEN_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	vSheenRoughnessMapUv = ( sheenRoughnessMapTransform * vec3( SHEEN_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULARMAP
	vSpecularMapUv = ( specularMapTransform * vec3( SPECULARMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_COLORMAP
	vSpecularColorMapUv = ( specularColorMapTransform * vec3( SPECULAR_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	vSpecularIntensityMapUv = ( specularIntensityMapTransform * vec3( SPECULAR_INTENSITYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_TRANSMISSIONMAP
	vTransmissionMapUv = ( transmissionMapTransform * vec3( TRANSMISSIONMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_THICKNESSMAP
	vThicknessMapUv = ( thicknessMapTransform * vec3( THICKNESSMAP_UV, 1 ) ).xy;
#endif`,lu=`#if defined( USE_ENVMAP ) || defined( DISTANCE ) || defined ( USE_SHADOWMAP ) || defined ( USE_TRANSMISSION ) || NUM_SPOT_LIGHT_COORDS > 0
	vec4 worldPosition = vec4( transformed, 1.0 );
	#ifdef USE_BATCHING
		worldPosition = batchingMatrix * worldPosition;
	#endif
	#ifdef USE_INSTANCING
		worldPosition = instanceMatrix * worldPosition;
	#endif
	worldPosition = modelMatrix * worldPosition;
#endif`,uu=`varying vec2 vUv;
uniform mat3 uvTransform;
void main() {
	vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	gl_Position = vec4( position.xy, 1.0, 1.0 );
}`,hu=`uniform sampler2D t2D;
uniform float backgroundIntensity;
varying vec2 vUv;
void main() {
	vec4 texColor = texture2D( t2D, vUv );
	#ifdef DECODE_VIDEO_TEXTURE
		texColor = vec4( mix( pow( texColor.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), texColor.rgb * 0.0773993808, vec3( lessThanEqual( texColor.rgb, vec3( 0.04045 ) ) ) ), texColor.w );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,fu=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,du=`#ifdef ENVMAP_TYPE_CUBE
	uniform samplerCube envMap;
#elif defined( ENVMAP_TYPE_CUBE_UV )
	uniform sampler2D envMap;
#endif
uniform float backgroundBlurriness;
uniform float backgroundIntensity;
uniform mat3 backgroundRotation;
varying vec3 vWorldDirection;
#include <cube_uv_reflection_fragment>
void main() {
	#ifdef ENVMAP_TYPE_CUBE
		vec4 texColor = textureCube( envMap, backgroundRotation * vWorldDirection );
	#elif defined( ENVMAP_TYPE_CUBE_UV )
		vec4 texColor = textureCubeUV( envMap, backgroundRotation * vWorldDirection, backgroundBlurriness );
	#else
		vec4 texColor = vec4( 0.0, 0.0, 0.0, 1.0 );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,pu=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,mu=`uniform samplerCube tCube;
uniform float tFlip;
uniform float opacity;
varying vec3 vWorldDirection;
void main() {
	vec4 texColor = textureCube( tCube, vec3( tFlip * vWorldDirection.x, vWorldDirection.yz ) );
	gl_FragColor = texColor;
	gl_FragColor.a *= opacity;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,gu=`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
varying vec2 vHighPrecisionZW;
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vHighPrecisionZW = gl_Position.zw;
}`,xu=`#if DEPTH_PACKING == 3200
	uniform float opacity;
#endif
#include <common>
#include <packing>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
varying vec2 vHighPrecisionZW;
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#if DEPTH_PACKING == 3200
		diffuseColor.a = opacity;
	#endif
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <logdepthbuf_fragment>
	#ifdef USE_REVERSED_DEPTH_BUFFER
		float fragCoordZ = vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ];
	#else
		float fragCoordZ = 0.5 * vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ] + 0.5;
	#endif
	#if DEPTH_PACKING == 3200
		gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );
	#elif DEPTH_PACKING == 3201
		gl_FragColor = packDepthToRGBA( fragCoordZ );
	#elif DEPTH_PACKING == 3202
		gl_FragColor = vec4( packDepthToRGB( fragCoordZ ), 1.0 );
	#elif DEPTH_PACKING == 3203
		gl_FragColor = vec4( packDepthToRG( fragCoordZ ), 0.0, 1.0 );
	#endif
}`,_u=`#define DISTANCE
varying vec3 vWorldPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <worldpos_vertex>
	#include <clipping_planes_vertex>
	vWorldPosition = worldPosition.xyz;
}`,yu=`#define DISTANCE
uniform vec3 referencePosition;
uniform float nearDistance;
uniform float farDistance;
varying vec3 vWorldPosition;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	float dist = length( vWorldPosition - referencePosition );
	dist = ( dist - nearDistance ) / ( farDistance - nearDistance );
	dist = saturate( dist );
	gl_FragColor = vec4( dist, 0.0, 0.0, 1.0 );
}`,vu=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
}`,Mu=`uniform sampler2D tEquirect;
varying vec3 vWorldDirection;
#include <common>
void main() {
	vec3 direction = normalize( vWorldDirection );
	vec2 sampleUV = equirectUv( direction );
	gl_FragColor = texture2D( tEquirect, sampleUV );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,bu=`uniform float scale;
attribute float lineDistance;
varying float vLineDistance;
#include <common>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	vLineDistance = scale * lineDistance;
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,Su=`uniform vec3 diffuse;
uniform float opacity;
uniform float dashSize;
uniform float totalSize;
varying float vLineDistance;
#include <common>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	if ( mod( vLineDistance, totalSize ) > dashSize ) {
		discard;
	}
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,Au=`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#if defined ( USE_ENVMAP ) || defined ( USE_SKINNING )
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinbase_vertex>
		#include <skinnormal_vertex>
		#include <defaultnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <fog_vertex>
}`,wu=`uniform vec3 diffuse;
uniform float opacity;
#ifndef FLAT_SHADED
	varying vec3 vNormal;
#endif
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <fog_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		reflectedLight.indirectDiffuse += lightMapTexel.rgb * lightMapIntensity * RECIPROCAL_PI;
	#else
		reflectedLight.indirectDiffuse += vec3( 1.0 );
	#endif
	#include <aomap_fragment>
	reflectedLight.indirectDiffuse *= diffuseColor.rgb;
	vec3 outgoingLight = reflectedLight.indirectDiffuse;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Tu=`#define LAMBERT
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,Eu=`#define LAMBERT
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_lambert_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_lambert_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Cu=`#define MATCAP
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <displacementmap_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
	vViewPosition = - mvPosition.xyz;
}`,Ru=`#define MATCAP
uniform vec3 diffuse;
uniform float opacity;
uniform sampler2D matcap;
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	vec3 viewDir = normalize( vViewPosition );
	vec3 x = normalize( vec3( viewDir.z, 0.0, - viewDir.x ) );
	vec3 y = cross( viewDir, x );
	vec2 uv = vec2( dot( x, normal ), dot( y, normal ) ) * 0.495 + 0.5;
	#ifdef USE_MATCAP
		vec4 matcapColor = texture2D( matcap, uv );
	#else
		vec4 matcapColor = vec4( vec3( mix( 0.2, 0.8, uv.y ) ), 1.0 );
	#endif
	vec3 outgoingLight = diffuseColor.rgb * matcapColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Iu=`#define NORMAL
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	vViewPosition = - mvPosition.xyz;
#endif
}`,Pu=`#define NORMAL
uniform float opacity;
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <uv_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 0.0, 0.0, 0.0, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	gl_FragColor = vec4( normalize( normal ) * 0.5 + 0.5, diffuseColor.a );
	#ifdef OPAQUE
		gl_FragColor.a = 1.0;
	#endif
}`,Lu=`#define PHONG
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,Nu=`#define PHONG
uniform vec3 diffuse;
uniform vec3 emissive;
uniform vec3 specular;
uniform float shininess;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_phong_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_phong_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + reflectedLight.directSpecular + reflectedLight.indirectSpecular + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Du=`#define STANDARD
varying vec3 vViewPosition;
#ifdef USE_TRANSMISSION
	varying vec3 vWorldPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
#ifdef USE_TRANSMISSION
	vWorldPosition = worldPosition.xyz;
#endif
}`,Uu=`#define STANDARD
#ifdef PHYSICAL
	#define IOR
	#define USE_SPECULAR
#endif
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float roughness;
uniform float metalness;
uniform float opacity;
#ifdef IOR
	uniform float ior;
#endif
#ifdef USE_SPECULAR
	uniform float specularIntensity;
	uniform vec3 specularColor;
	#ifdef USE_SPECULAR_COLORMAP
		uniform sampler2D specularColorMap;
	#endif
	#ifdef USE_SPECULAR_INTENSITYMAP
		uniform sampler2D specularIntensityMap;
	#endif
#endif
#ifdef USE_CLEARCOAT
	uniform float clearcoat;
	uniform float clearcoatRoughness;
#endif
#ifdef USE_DISPERSION
	uniform float dispersion;
#endif
#ifdef USE_IRIDESCENCE
	uniform float iridescence;
	uniform float iridescenceIOR;
	uniform float iridescenceThicknessMinimum;
	uniform float iridescenceThicknessMaximum;
#endif
#ifdef USE_SHEEN
	uniform vec3 sheenColor;
	uniform float sheenRoughness;
	#ifdef USE_SHEEN_COLORMAP
		uniform sampler2D sheenColorMap;
	#endif
	#ifdef USE_SHEEN_ROUGHNESSMAP
		uniform sampler2D sheenRoughnessMap;
	#endif
#endif
#ifdef USE_ANISOTROPY
	uniform vec2 anisotropyVector;
	#ifdef USE_ANISOTROPYMAP
		uniform sampler2D anisotropyMap;
	#endif
#endif
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <iridescence_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_physical_pars_fragment>
#include <transmission_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <clearcoat_pars_fragment>
#include <iridescence_pars_fragment>
#include <roughnessmap_pars_fragment>
#include <metalnessmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <roughnessmap_fragment>
	#include <metalnessmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <clearcoat_normal_fragment_begin>
	#include <clearcoat_normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_physical_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 totalDiffuse = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse;
	vec3 totalSpecular = reflectedLight.directSpecular + reflectedLight.indirectSpecular;
	#include <transmission_fragment>
	vec3 outgoingLight = totalDiffuse + totalSpecular + totalEmissiveRadiance;
	#ifdef USE_SHEEN
 
		outgoingLight = outgoingLight + sheenSpecularDirect + sheenSpecularIndirect;
 
 	#endif
	#ifdef USE_CLEARCOAT
		float dotNVcc = saturate( dot( geometryClearcoatNormal, geometryViewDir ) );
		vec3 Fcc = F_Schlick( material.clearcoatF0, material.clearcoatF90, dotNVcc );
		outgoingLight = outgoingLight * ( 1.0 - material.clearcoat * Fcc ) + ( clearcoatSpecularDirect + clearcoatSpecularIndirect ) * material.clearcoat;
	#endif
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Fu=`#define TOON
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,Ou=`#define TOON
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <gradientmap_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_toon_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_toon_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Bu=`uniform float size;
uniform float scale;
#include <common>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
#ifdef USE_POINTS_UV
	varying vec2 vUv;
	uniform mat3 uvTransform;
#endif
void main() {
	#ifdef USE_POINTS_UV
		vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	#endif
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	gl_PointSize = size;
	#ifdef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) gl_PointSize *= ( scale / - mvPosition.z );
	#endif
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <fog_vertex>
}`,zu=`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <color_pars_fragment>
#include <map_particle_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_particle_fragment>
	#include <color_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,ku=`#include <common>
#include <batching_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <shadowmap_pars_vertex>
void main() {
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,Vu=`uniform vec3 color;
uniform float opacity;
#include <common>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <logdepthbuf_pars_fragment>
#include <shadowmap_pars_fragment>
#include <shadowmask_pars_fragment>
void main() {
	#include <logdepthbuf_fragment>
	gl_FragColor = vec4( color, opacity * ( 1.0 - getShadowMask() ) );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,Gu=`uniform float rotation;
uniform vec2 center;
#include <common>
#include <uv_pars_vertex>
#include <fog_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	vec4 mvPosition = modelViewMatrix[ 3 ];
	vec2 scale = vec2( length( modelMatrix[ 0 ].xyz ), length( modelMatrix[ 1 ].xyz ) );
	#ifndef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) scale *= - mvPosition.z;
	#endif
	vec2 alignedPosition = ( position.xy - ( center - vec2( 0.5 ) ) ) * scale;
	vec2 rotatedPosition;
	rotatedPosition.x = cos( rotation ) * alignedPosition.x - sin( rotation ) * alignedPosition.y;
	rotatedPosition.y = sin( rotation ) * alignedPosition.x + cos( rotation ) * alignedPosition.y;
	mvPosition.xy += rotatedPosition;
	gl_Position = projectionMatrix * mvPosition;
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,Hu=`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
}`,Z={alphahash_fragment:uc,alphahash_pars_fragment:hc,alphamap_fragment:fc,alphamap_pars_fragment:dc,alphatest_fragment:pc,alphatest_pars_fragment:mc,aomap_fragment:gc,aomap_pars_fragment:xc,batching_pars_vertex:_c,batching_vertex:yc,begin_vertex:vc,beginnormal_vertex:Mc,bsdfs:bc,iridescence_fragment:Sc,bumpmap_pars_fragment:Ac,clipping_planes_fragment:wc,clipping_planes_pars_fragment:Tc,clipping_planes_pars_vertex:Ec,clipping_planes_vertex:Cc,color_fragment:Rc,color_pars_fragment:Ic,color_pars_vertex:Pc,color_vertex:Lc,common:Nc,cube_uv_reflection_fragment:Dc,defaultnormal_vertex:Uc,displacementmap_pars_vertex:Fc,displacementmap_vertex:Oc,emissivemap_fragment:Bc,emissivemap_pars_fragment:zc,colorspace_fragment:kc,colorspace_pars_fragment:Vc,envmap_fragment:Gc,envmap_common_pars_fragment:Hc,envmap_pars_fragment:Wc,envmap_pars_vertex:Xc,envmap_physical_pars_fragment:nl,envmap_vertex:qc,fog_vertex:$c,fog_pars_vertex:Yc,fog_fragment:Zc,fog_pars_fragment:Jc,gradientmap_pars_fragment:Kc,lightmap_pars_fragment:jc,lights_lambert_fragment:Qc,lights_lambert_pars_fragment:tl,lights_pars_begin:el,lights_toon_fragment:il,lights_toon_pars_fragment:sl,lights_phong_fragment:rl,lights_phong_pars_fragment:ol,lights_physical_fragment:al,lights_physical_pars_fragment:cl,lights_fragment_begin:ll,lights_fragment_maps:ul,lights_fragment_end:hl,lightprobes_pars_fragment:fl,logdepthbuf_fragment:dl,logdepthbuf_pars_fragment:pl,logdepthbuf_pars_vertex:ml,logdepthbuf_vertex:gl,map_fragment:xl,map_pars_fragment:_l,map_particle_fragment:yl,map_particle_pars_fragment:vl,metalnessmap_fragment:Ml,metalnessmap_pars_fragment:bl,morphinstance_vertex:Sl,morphcolor_vertex:Al,morphnormal_vertex:wl,morphtarget_pars_vertex:Tl,morphtarget_vertex:El,normal_fragment_begin:Cl,normal_fragment_maps:Rl,normal_pars_fragment:Il,normal_pars_vertex:Pl,normal_vertex:Ll,normalmap_pars_fragment:Nl,clearcoat_normal_fragment_begin:Dl,clearcoat_normal_fragment_maps:Ul,clearcoat_pars_fragment:Fl,iridescence_pars_fragment:Ol,opaque_fragment:Bl,packing:zl,premultiplied_alpha_fragment:kl,project_vertex:Vl,dithering_fragment:Gl,dithering_pars_fragment:Hl,roughnessmap_fragment:Wl,roughnessmap_pars_fragment:Xl,shadowmap_pars_fragment:ql,shadowmap_pars_vertex:$l,shadowmap_vertex:Yl,shadowmask_pars_fragment:Zl,skinbase_vertex:Jl,skinning_pars_vertex:Kl,skinning_vertex:jl,skinnormal_vertex:Ql,specularmap_fragment:tu,specularmap_pars_fragment:eu,tonemapping_fragment:nu,tonemapping_pars_fragment:iu,transmission_fragment:su,transmission_pars_fragment:ru,uv_pars_fragment:ou,uv_pars_vertex:au,uv_vertex:cu,worldpos_vertex:lu,background_vert:uu,background_frag:hu,backgroundCube_vert:fu,backgroundCube_frag:du,cube_vert:pu,cube_frag:mu,depth_vert:gu,depth_frag:xu,distance_vert:_u,distance_frag:yu,equirect_vert:vu,equirect_frag:Mu,linedashed_vert:bu,linedashed_frag:Su,meshbasic_vert:Au,meshbasic_frag:wu,meshlambert_vert:Tu,meshlambert_frag:Eu,meshmatcap_vert:Cu,meshmatcap_frag:Ru,meshnormal_vert:Iu,meshnormal_frag:Pu,meshphong_vert:Lu,meshphong_frag:Nu,meshphysical_vert:Du,meshphysical_frag:Uu,meshtoon_vert:Fu,meshtoon_frag:Ou,points_vert:Bu,points_frag:zu,shadow_vert:ku,shadow_frag:Vu,sprite_vert:Gu,sprite_frag:Hu},G={common:{diffuse:{value:new xt(16777215)},opacity:{value:1},map:{value:null},mapTransform:{value:new Y},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0}},specularmap:{specularMap:{value:null},specularMapTransform:{value:new Y}},envmap:{envMap:{value:null},envMapRotation:{value:new Y},reflectivity:{value:1},ior:{value:1.5},refractionRatio:{value:.98},dfgLUT:{value:null}},aomap:{aoMap:{value:null},aoMapIntensity:{value:1},aoMapTransform:{value:new Y}},lightmap:{lightMap:{value:null},lightMapIntensity:{value:1},lightMapTransform:{value:new Y}},bumpmap:{bumpMap:{value:null},bumpMapTransform:{value:new Y},bumpScale:{value:1}},normalmap:{normalMap:{value:null},normalMapTransform:{value:new Y},normalScale:{value:new mt(1,1)}},displacementmap:{displacementMap:{value:null},displacementMapTransform:{value:new Y},displacementScale:{value:1},displacementBias:{value:0}},emissivemap:{emissiveMap:{value:null},emissiveMapTransform:{value:new Y}},metalnessmap:{metalnessMap:{value:null},metalnessMapTransform:{value:new Y}},roughnessmap:{roughnessMap:{value:null},roughnessMapTransform:{value:new Y}},gradientmap:{gradientMap:{value:null}},fog:{fogDensity:{value:25e-5},fogNear:{value:1},fogFar:{value:2e3},fogColor:{value:new xt(16777215)}},lights:{ambientLightColor:{value:[]},lightProbe:{value:[]},directionalLights:{value:[],properties:{direction:{},color:{}}},directionalLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},directionalShadowMatrix:{value:[]},spotLights:{value:[],properties:{color:{},position:{},direction:{},distance:{},coneCos:{},penumbraCos:{},decay:{}}},spotLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},spotLightMap:{value:[]},spotLightMatrix:{value:[]},pointLights:{value:[],properties:{color:{},position:{},decay:{},distance:{}}},pointLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{},shadowCameraNear:{},shadowCameraFar:{}}},pointShadowMatrix:{value:[]},hemisphereLights:{value:[],properties:{direction:{},skyColor:{},groundColor:{}}},rectAreaLights:{value:[],properties:{color:{},position:{},width:{},height:{}}},ltc_1:{value:null},ltc_2:{value:null},probesSH:{value:null},probesMin:{value:new V},probesMax:{value:new V},probesResolution:{value:new V}},points:{diffuse:{value:new xt(16777215)},opacity:{value:1},size:{value:1},scale:{value:1},map:{value:null},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0},uvTransform:{value:new Y}},sprite:{diffuse:{value:new xt(16777215)},opacity:{value:1},center:{value:new mt(.5,.5)},rotation:{value:0},map:{value:null},mapTransform:{value:new Y},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0}}},kr={basic:{uniforms:bt([G.common,G.specularmap,G.envmap,G.aomap,G.lightmap,G.fog]),vertexShader:Z.meshbasic_vert,fragmentShader:Z.meshbasic_frag},lambert:{uniforms:bt([G.common,G.specularmap,G.envmap,G.aomap,G.lightmap,G.emissivemap,G.bumpmap,G.normalmap,G.displacementmap,G.fog,G.lights,{emissive:{value:new xt(0)},envMapIntensity:{value:1}}]),vertexShader:Z.meshlambert_vert,fragmentShader:Z.meshlambert_frag},phong:{uniforms:bt([G.common,G.specularmap,G.envmap,G.aomap,G.lightmap,G.emissivemap,G.bumpmap,G.normalmap,G.displacementmap,G.fog,G.lights,{emissive:{value:new xt(0)},specular:{value:new xt(1118481)},shininess:{value:30},envMapIntensity:{value:1}}]),vertexShader:Z.meshphong_vert,fragmentShader:Z.meshphong_frag},standard:{uniforms:bt([G.common,G.envmap,G.aomap,G.lightmap,G.emissivemap,G.bumpmap,G.normalmap,G.displacementmap,G.roughnessmap,G.metalnessmap,G.fog,G.lights,{emissive:{value:new xt(0)},roughness:{value:1},metalness:{value:0},envMapIntensity:{value:1}}]),vertexShader:Z.meshphysical_vert,fragmentShader:Z.meshphysical_frag},toon:{uniforms:bt([G.common,G.aomap,G.lightmap,G.emissivemap,G.bumpmap,G.normalmap,G.displacementmap,G.gradientmap,G.fog,G.lights,{emissive:{value:new xt(0)}}]),vertexShader:Z.meshtoon_vert,fragmentShader:Z.meshtoon_frag},matcap:{uniforms:bt([G.common,G.bumpmap,G.normalmap,G.displacementmap,G.fog,{matcap:{value:null}}]),vertexShader:Z.meshmatcap_vert,fragmentShader:Z.meshmatcap_frag},points:{uniforms:bt([G.points,G.fog]),vertexShader:Z.points_vert,fragmentShader:Z.points_frag},dashed:{uniforms:bt([G.common,G.fog,{scale:{value:1},dashSize:{value:1},totalSize:{value:2}}]),vertexShader:Z.linedashed_vert,fragmentShader:Z.linedashed_frag},depth:{uniforms:bt([G.common,G.displacementmap]),vertexShader:Z.depth_vert,fragmentShader:Z.depth_frag},normal:{uniforms:bt([G.common,G.bumpmap,G.normalmap,G.displacementmap,{opacity:{value:1}}]),vertexShader:Z.meshnormal_vert,fragmentShader:Z.meshnormal_frag},sprite:{uniforms:bt([G.sprite,G.fog]),vertexShader:Z.sprite_vert,fragmentShader:Z.sprite_frag},background:{uniforms:{uvTransform:{value:new Y},t2D:{value:null},backgroundIntensity:{value:1}},vertexShader:Z.background_vert,fragmentShader:Z.background_frag},backgroundCube:{uniforms:{envMap:{value:null},backgroundBlurriness:{value:0},backgroundIntensity:{value:1},backgroundRotation:{value:new Y}},vertexShader:Z.backgroundCube_vert,fragmentShader:Z.backgroundCube_frag},cube:{uniforms:{tCube:{value:null},tFlip:{value:-1},opacity:{value:1}},vertexShader:Z.cube_vert,fragmentShader:Z.cube_frag},equirect:{uniforms:{tEquirect:{value:null}},vertexShader:Z.equirect_vert,fragmentShader:Z.equirect_frag},distance:{uniforms:bt([G.common,G.displacementmap,{referencePosition:{value:new V},nearDistance:{value:1},farDistance:{value:1e3}}]),vertexShader:Z.distance_vert,fragmentShader:Z.distance_frag},shadow:{uniforms:bt([G.lights,G.fog,{color:{value:new xt(0)},opacity:{value:1}}]),vertexShader:Z.shadow_vert,fragmentShader:Z.shadow_frag}};kr.physical={uniforms:bt([kr.standard.uniforms,{clearcoat:{value:0},clearcoatMap:{value:null},clearcoatMapTransform:{value:new Y},clearcoatNormalMap:{value:null},clearcoatNormalMapTransform:{value:new Y},clearcoatNormalScale:{value:new mt(1,1)},clearcoatRoughness:{value:0},clearcoatRoughnessMap:{value:null},clearcoatRoughnessMapTransform:{value:new Y},dispersion:{value:0},iridescence:{value:0},iridescenceMap:{value:null},iridescenceMapTransform:{value:new Y},iridescenceIOR:{value:1.3},iridescenceThicknessMinimum:{value:100},iridescenceThicknessMaximum:{value:400},iridescenceThicknessMap:{value:null},iridescenceThicknessMapTransform:{value:new Y},sheen:{value:0},sheenColor:{value:new xt(0)},sheenColorMap:{value:null},sheenColorMapTransform:{value:new Y},sheenRoughness:{value:1},sheenRoughnessMap:{value:null},sheenRoughnessMapTransform:{value:new Y},transmission:{value:0},transmissionMap:{value:null},transmissionMapTransform:{value:new Y},transmissionSamplerSize:{value:new mt},transmissionSamplerMap:{value:null},thickness:{value:0},thicknessMap:{value:null},thicknessMapTransform:{value:new Y},attenuationDistance:{value:0},attenuationColor:{value:new xt(0)},specularColor:{value:new xt(1,1,1)},specularColorMap:{value:null},specularColorMapTransform:{value:new Y},specularIntensity:{value:1},specularIntensityMap:{value:null},specularIntensityMapTransform:{value:new Y},anisotropyVector:{value:new mt},anisotropyMap:{value:null},anisotropyMapTransform:{value:new Y}}]),vertexShader:Z.meshphysical_vert,fragmentShader:Z.meshphysical_frag};var Wu=new Y;Wu.set(-1,0,0,0,1,0,0,0,1);var T_={[cs]:"LINEAR_TONE_MAPPING",[ls]:"REINHARD_TONE_MAPPING",[us]:"CINEON_TONE_MAPPING",[hs]:"ACES_FILMIC_TONE_MAPPING",[ds]:"AGX_TONE_MAPPING",[ps]:"NEUTRAL_TONE_MAPPING",[fs]:"CUSTOM_TONE_MAPPING"};var E_=new Float32Array(16),C_=new Float32Array(9),R_=new Float32Array(4);var I_={[cs]:"Linear",[ls]:"Reinhard",[us]:"Cineon",[hs]:"ACESFilmic",[ds]:"AgX",[ps]:"Neutral",[fs]:"Custom"};var P_={[vr]:"SHADOWMAP_TYPE_PCF",[Mr]:"SHADOWMAP_TYPE_VSM"};var L_={[wr]:"ENVMAP_TYPE_CUBE",[gs]:"ENVMAP_TYPE_CUBE",[Tr]:"ENVMAP_TYPE_CUBE_UV"};var N_={[gs]:"ENVMAP_MODE_REFRACTION"};var D_={[br]:"ENVMAP_BLENDING_MULTIPLY",[Sr]:"ENVMAP_BLENDING_MIX",[Ar]:"ENVMAP_BLENDING_ADD"};var Xu=new Y;Xu.set(-1,0,0,0,1,0,0,0,1);var U_=new Uint16Array([12469,15057,12620,14925,13266,14620,13807,14376,14323,13990,14545,13625,14713,13328,14840,12882,14931,12528,14996,12233,15039,11829,15066,11525,15080,11295,15085,10976,15082,10705,15073,10495,13880,14564,13898,14542,13977,14430,14158,14124,14393,13732,14556,13410,14702,12996,14814,12596,14891,12291,14937,11834,14957,11489,14958,11194,14943,10803,14921,10506,14893,10278,14858,9960,14484,14039,14487,14025,14499,13941,14524,13740,14574,13468,14654,13106,14743,12678,14818,12344,14867,11893,14889,11509,14893,11180,14881,10751,14852,10428,14812,10128,14765,9754,14712,9466,14764,13480,14764,13475,14766,13440,14766,13347,14769,13070,14786,12713,14816,12387,14844,11957,14860,11549,14868,11215,14855,10751,14825,10403,14782,10044,14729,9651,14666,9352,14599,9029,14967,12835,14966,12831,14963,12804,14954,12723,14936,12564,14917,12347,14900,11958,14886,11569,14878,11247,14859,10765,14828,10401,14784,10011,14727,9600,14660,9289,14586,8893,14508,8533,15111,12234,15110,12234,15104,12216,15092,12156,15067,12010,15028,11776,14981,11500,14942,11205,14902,10752,14861,10393,14812,9991,14752,9570,14682,9252,14603,8808,14519,8445,14431,8145,15209,11449,15208,11451,15202,11451,15190,11438,15163,11384,15117,11274,15055,10979,14994,10648,14932,10343,14871,9936,14803,9532,14729,9218,14645,8742,14556,8381,14461,8020,14365,7603,15273,10603,15272,10607,15267,10619,15256,10631,15231,10614,15182,10535,15118,10389,15042,10167,14963,9787,14883,9447,14800,9115,14710,8665,14615,8318,14514,7911,14411,7507,14279,7198,15314,9675,15313,9683,15309,9712,15298,9759,15277,9797,15229,9773,15166,9668,15084,9487,14995,9274,14898,8910,14800,8539,14697,8234,14590,7790,14479,7409,14367,7067,14178,6621,15337,8619,15337,8631,15333,8677,15325,8769,15305,8871,15264,8940,15202,8909,15119,8775,15022,8565,14916,8328,14804,8009,14688,7614,14569,7287,14448,6888,14321,6483,14088,6171,15350,7402,15350,7419,15347,7480,15340,7613,15322,7804,15287,7973,15229,8057,15148,8012,15046,7846,14933,7611,14810,7357,14682,7069,14552,6656,14421,6316,14251,5948,14007,5528,15356,5942,15356,5977,15353,6119,15348,6294,15332,6551,15302,6824,15249,7044,15171,7122,15070,7050,14949,6861,14818,6611,14679,6349,14538,6067,14398,5651,14189,5311,13935,4958,15359,4123,15359,4153,15356,4296,15353,4646,15338,5160,15311,5508,15263,5829,15188,6042,15088,6094,14966,6001,14826,5796,14678,5543,14527,5287,14377,4985,14133,4586,13869,4257,15360,1563,15360,1642,15358,2076,15354,2636,15341,3350,15317,4019,15273,4429,15203,4732,15105,4911,14981,4932,14836,4818,14679,4621,14517,4386,14359,4156,14083,3795,13808,3437,15360,122,15360,137,15358,285,15355,636,15344,1274,15322,2177,15281,2765,15215,3223,15120,3451,14995,3569,14846,3567,14681,3466,14511,3305,14344,3121,14037,2800,13753,2467,15360,0,15360,1,15359,21,15355,89,15346,253,15325,479,15287,796,15225,1148,15133,1492,15008,1749,14856,1882,14685,1886,14506,1783,14324,1608,13996,1398,13702,1183]);function vs(i,t,e,n){let s=e;if(n>=i[s])return s-1;if(n<=i[t])return t;let r=t,o=s,a=r+o>>1;for(;n<i[a]||n>=i[a+1];)n<i[a]?o=a:r=a,a=r+o>>1;return a}p(vs,"findSpan");var Vr=new Map;function Mn(i,t){let e=Vr.get(t);e||Vr.set(t,e=[]);let n=e[i];return n||(e[i]=n=new Float64Array(t)),n}p(Mn,"scratch");function Ms(i,t,e,n,s){let r=Mn(0,t+1),o=Mn(1,t+1);s[0]=1;for(let a=1;a<=t;a+=1){r[a]=n-i[e+1-a],o[a]=i[e+a]-n;let c=0;for(let l=0;l<a;l+=1){let u=s[l]/(o[l+1]+r[a-l]);s[l]=c+o[l+1]*u,c=r[a-l]*u}s[a]=c}return s}p(Ms,"basisFunctions");function Gr(i,t,e,n){let s=i.deg,r=se(t,i.poles),o=se(t,i.knots),a=i.weights?se(t,i.weights):null;if(i.period){let[f,d]=i.range;(e>d||e<f)&&(e=f+((e-f)%i.period+i.period)%i.period)}let c=vs(o,s,i.n,e),l=Ms(o,s,c,e,Mn(2,s+1)),u=[0,0,0],h=0;for(let f=0;f<=s;f+=1){let d=c-s+f,m=a?a[d]:1,g=l[f]*m;for(let _=0;_<n;_+=1)u[_]+=g*r[d*n+_];h+=g}for(let f=0;f<n;f+=1)u[f]/=h;return u.slice(0,n)}p(Gr,"evaluateBSplineCurve");var qu={line(i,t){let{origin:e,dir:n}=i;return[e[0]+t*n[0],e[1]+t*n[1],e[2]+t*n[2]]},circle(i,t){let e=Math.cos(t)*i.radius,n=Math.sin(t)*i.radius;return Se(i,e,n,0)},ellipse(i,t){let e=Math.cos(t)*i.majorRadius,n=Math.sin(t)*i.minorRadius;return Se(i,e,n,0)}};function Yt(i,t,e){let n=qu[i.kind];if(n)return n(i,e);if(i.kind==="bspline")return Gr(i,t,e,3);throw new Error(`unknown curve kind ${i.kind}`)}p(Yt,"evaluateCurve3");function bn(i,t,e){return Gr(i,t,e,2)}p(bn,"evaluatePCurve");function Se(i,t,e,n){let{origin:s,xdir:r,ydir:o,zdir:a}=i;return[s[0]+t*r[0]+e*o[0]+n*a[0],s[1]+t*r[1]+e*o[1]+n*a[1],s[2]+t*r[2]+e*o[2]+n*a[2]]}p(Se,"frameMix");function $u(i,t,e,n){let{degU:s,degV:r,nu:o,nv:a}=i,c=se(t,i.poles),l=se(t,i.knotsU),u=se(t,i.knotsV),h=i.weights?se(t,i.weights):null,f=vs(l,s,o,e),d=vs(u,r,a,n),m=Ms(l,s,f,e,Mn(2,s+1)),g=Ms(u,r,d,n,Mn(3,r+1)),_=0,x=0,y=0,v=0;for(let b=0;b<=s;b+=1){let S=f-s+b;for(let A=0;A<=r;A+=1){let M=d-r+A,w=S*a+M,I=h?h[w]:1,E=m[b]*g[A]*I;_+=E*c[w*3],x+=E*c[w*3+1],y+=E*c[w*3+2],v+=E}}return[_/v,x/v,y/v]}p($u,"evaluateNurbsSurface");var Yu={plane(i,t,e){return Se(i,t,e,0)},cylinder(i,t,e){let n=i.radius;return Se(i,n*Math.cos(t),n*Math.sin(t),e)},cone(i,t,e){let n=i.radius+e*Math.sin(i.semiAngle);return Math.abs(n)<(Math.abs(i.radius)+Math.abs(e))*Number.EPSILON*4&&(n=0),Se(i,n*Math.cos(t),n*Math.sin(t),e*Math.cos(i.semiAngle))},sphere(i,t,e){let n=i.radius,s=Math.abs(Math.cos(e))<Number.EPSILON*4?0:Math.cos(e);return Se(i,n*s*Math.cos(t),n*s*Math.sin(t),n*Math.sin(e))},torus(i,t,e){let n=i.majorRadius+i.minorRadius*Math.cos(e);return Se(i,n*Math.cos(t),n*Math.sin(t),i.minorRadius*Math.sin(e))}};function lt(i,t,e,n){let s=Yu[i.kind];if(s)return s(i,e,n);if(i.kind==="nurbs")return $u(i,t,e,n);if(i.kind==="revolution"){let r=Yt(i.profile,t,n);return Zu(r,i.origin,i.dir,e)}if(i.kind==="extrusion"){let r=Yt(i.profile,t,e);return[r[0]+n*i.dir[0],r[1]+n*i.dir[1],r[2]+n*i.dir[2]]}throw new Error(`unknown surface kind ${i.kind}`)}p(lt,"evaluateSurface");function Zu(i,t,e,n){let s=i[0]-t[0],r=i[1]-t[1],o=i[2]-t[2],[a,c,l]=e,u=Math.cos(n),h=Math.sin(n),f=a*s+c*r+l*o,d=c*o-l*r,m=l*s-a*o,g=a*r-c*s;return[t[0]+s*u+d*h+a*f*(1-u),t[1]+r*u+m*h+c*f*(1-u),t[2]+o*u+g*h+l*f*(1-u)]}p(Zu,"rotateAroundAxis");function Sn(i,t,e,n,s,r){if(["plane","cylinder","cone","sphere","torus"].includes(i.kind)){let{xdir:M,ydir:w,zdir:I}=i,E=[M[1]*w[2]-M[2]*w[1],M[2]*w[0]-M[0]*w[2],M[0]*w[1]-M[1]*w[0]],L=E[0]*I[0]+E[1]*I[1]+E[2]*I[2]<0?-1:1,D=0,R=0,C=1;if(i.kind!=="plane"){let T=i.kind==="cone"?-i.semiAngle:i.kind==="cylinder"?0:n;D=Math.cos(e)*Math.cos(T),R=Math.sin(e)*Math.cos(T),C=Math.sin(T)}let P=(r?-1:1)*L;return[0,1,2].map(T=>P*(D*M[T]+R*w[T]+C*I[T]))}let[o,a,c,l]=s,u=Math.max((a-o)*1e-4,1e-7),h=Math.max((l-c)*1e-4,1e-7),f=lt(i,t,e-u,n),d=lt(i,t,e+u,n),m=lt(i,t,e,n-h),g=lt(i,t,e,n+h),_=[d[0]-f[0],d[1]-f[1],d[2]-f[2]],x=[g[0]-m[0],g[1]-m[1],g[2]-m[2]],y=_[1]*x[2]-_[2]*x[1],v=_[2]*x[0]-_[0]*x[2],b=_[0]*x[1]-_[1]*x[0],S=Math.hypot(y,v,b)||1,A=r?-1:1;return y=y/S*A,v=v/S*A,b=b/S*A,[y,v,b]}p(Sn,"evaluateSurfaceNormal");var pe=2,Vt={chordTolerance:.0015,loopTolerance:5e-4,angleTolerance:.35,maxRefineDepth:7,minLoopSegments:8};function tt(i,t){return[i[0]-t[0],i[1]-t[1],i[2]-t[2]]}p(tt,"sub");function et(i){return Math.hypot(i[0],i[1],i[2])}p(et,"length3");function An(i,t){return i.kind==="sphere"?Math.abs(Math.cos(t))<1e-12:i.kind==="cone"?Math.abs(i.radius+t*Math.sin(i.semiAngle))<(Math.abs(i.radius)+Math.abs(t))*1e-12:!1}p(An,"singularU");function Hr(i,t,e,n,s){let r=[],o=[],a=[],c=[];for(let l=0;i.surface.kind!=="plane"&&l<2;l+=1){let u=i.uv[l*2],h=i.uv[l*2+1];c.push({d:l,lo:u,hi:h,epsilon:Math.max(Math.abs(u),Math.abs(h),h-u,1e-12)*2**-23})}for(let l of t){let u=!l.reversed,h=l.edgeOrd?s?.get(l.edgeOrd):null,f=null,d=null;if(h&&h.points.length>=2){let m=Ku(i,l,e,n,h);m&&(f=m.uvs,d=m.fractions)}f||(f=Ju(i,l,e,n));for(let m of f)for(let{d:g,lo:_,hi:x,epsilon:y}of c)Math.abs(m[g]-_)<=y?m[g]=_:Math.abs(m[g]-x)<=y&&(m[g]=x);u||(f.reverse(),d?.reverse());for(let m=0;m<f.length-1;m+=1)r.push(f[m]),o.push(l.edgeOrd||0),a.push(d?{ord:l.edgeOrd,f0:d[m],f1:d[m+1]}:null)}return r.segmentOrds=o,r.segmentMeta=a,r}p(Hr,"sampleLoopPolygon");function qr(i,t,e,n){let[s,r]=t.range,o=i.surface,a=p(g=>bn(t,e,g),"uvOf"),c=p(g=>lt(o,e,g[0],g[1]),"xyzOf"),l=c(a(s)),u=c(a(r)),h=et(tt(l,u))<=n,f=Math.max(h?Vt.minLoopSegments:2,t.n??2),d=[];for(let g=0;g<=f;g+=1)d.push(s+(r-s)*g/f);let m=0;for(;m<Vt.maxRefineDepth;){let g=!1,_=[d[0]];for(let x=0;x+1<d.length;x+=1){let y=d[x],v=d[x+1],b=(y+v)/2,S=c(a(y)),A=c(a(v)),M=c(a(b)),w=[(S[0]+A[0])/2,(S[1]+A[1])/2,(S[2]+A[2])/2];et(tt(M,w))>n&&(_.push(b),g=!0),_.push(v)}if(d.length=0,d.push(..._),!g)break;m+=1}return{params:d,uvs:d.map(a)}}p(qr,"samplePCurveParams");function Ju(i,t,e,n){return qr(i,t,e,n).uvs}p(Ju,"samplePCurveAdaptive");function Ku(i,t,e,n,s){let r=qr(i,t,e,n);if(r.uvs.length<2)return null;let o=i.surface,a=r.uvs.map(S=>lt(o,e,S[0],S[1])),c=[0];for(let S=1;S<a.length;S+=1)c.push(c[S-1]+et(tt(a[S],a[S-1])));let l=c[c.length-1];if(!(l>0))return null;for(let S=0;S<c.length;S+=1)c[S]/=l;let u=s.points[0],h=s.points[s.points.length-1],f=et(tt(u,a[0]))+et(tt(h,a[a.length-1])),m=et(tt(u,a[a.length-1]))+et(tt(h,a[0]))<f,g=[],_=[],x=[],y=s.boundarySubset||s.points.map((S,A)=>A),v=y.length,b=0;for(let S=0;S<v;S+=1){let A=y[m?v-1-S:S],M=s.fractions[A],w=m?1-M:M;for(;b+1<c.length-1&&c[b+1]<w;)b+=1;let I;if(S===0)I=r.params[0];else if(S===v-1)I=r.params[r.params.length-1];else{let R=c[b],C=c[b+1],P=C>R?(w-R)/(C-R):0;I=r.params[b]+P*(r.params[b+1]-r.params[b])}let E=bn(t,e,I),L=s.points[A],D=lt(o,e,E[0],E[1]);if(et(tt(D,L))>n*2)return null;g.push(E),_.push(M),x.push(I)}if(o.kind!=="plane"){let S=g.map(A=>lt(o,e,A[0],A[1]));for(let A=0;A<4;A+=1){let M=!1,w=[g[0]],I=[_[0]],E=[x[0]],L=[S[0]];for(let D=0;D+1<g.length;D+=1){let R=S[D],C=S[D+1],P=(x[D]+x[D+1])/2,T=bn(t,e,P),U=lt(o,e,T[0],T[1]),F=[(R[0]+C[0])/2,(R[1]+C[1])/2,(R[2]+C[2])/2];et(tt(U,F))>n&&(w.push(T),I.push((_[D]+_[D+1])/2),E.push(P),L.push(U),M=!0),w.push(g[D+1]),I.push(_[D+1]),E.push(x[D+1]),L.push(S[D+1])}if(g.length=0,_.length=0,x.length=0,S.length=0,g.push(...w),_.push(...I),x.push(...E),S.push(...L),!M)break}}return{uvs:g,fractions:_}}p(Ku,"mapSharedEdgeToPCurve");function li(i,t,e){let n=i.fractions,s=n.length-1;if(t<=n[0])return i.points[0];if(t>=n[s])return i.points[s];let r=0,o=s;for(;r+1<o;){let f=r+o>>1;n[f]<=t?r=f:o=f}let a=n[r],c=n[r+1];if(t===a)return i.points[r];if(t===c)return i.points[r+1];let l=c>a?(t-a)/(c-a):0;if(i.curve&&e){let f=i.params[r]+l*(i.params[r+1]-i.params[r]);return Yt(i.curve,e,f)}let u=i.points[r],h=i.points[r+1];return[u[0]+l*(h[0]-u[0]),u[1]+l*(h[1]-u[1]),u[2]+l*(h[2]-u[2])]}p(li,"edgePointAt");function ju(i,t,e){let[n,s]=i.range,r=Yt(i,t,n),o=Yt(i,t,s),a=!1;if(i.kind!=="line"){let g=et(tt(r,o));for(let _ of[.25,.5,.75])g=Math.max(g,et(tt(r,Yt(i,t,n+_*(s-n)))));a=et(tt(r,o))<=g*2**-21}let c=i.kind==="line"?1:Math.max(a?8:4,i.n??2),l=[];for(let g=0;g<=c;g+=1)l.push(n+(s-n)*g/c);let u=0;for(;u<Vt.maxRefineDepth;){let g=!1,_=[l[0]];for(let x=0;x+1<l.length;x+=1){let y=l[x],v=l[x+1],b=(y+v)/2,S=Yt(i,t,y),A=Yt(i,t,v),M=Yt(i,t,b),w=[(S[0]+A[0])/2,(S[1]+A[1])/2,(S[2]+A[2])/2];et(tt(M,w))>e&&(_.push(b),g=!0),_.push(v)}if(l.length=0,l.push(..._),!g)break;u+=1}let h=l.map(g=>Yt(i,t,g));a&&h.length>1&&(h[h.length-1]=h[0]);let f=[0];for(let g=1;g<h.length;g+=1)f.push(f[g-1]+et(tt(h[g],h[g-1])));let d=f[f.length-1];if(d>0){for(let g=0;g<f.length;g+=1)f[g]/=d;f[f.length-1]=1}let m=[0];{let g=e*(Vt.loopTolerance/Vt.chordTolerance),_=0;for(let x=1;x<h.length;x+=1){if(x===h.length-1){m.push(x);break}let y=h[_],v=h[x+1],b=0;for(let S=_+1;S<=x;S+=1){let A=tt(h[S],y),M=tt(v,y),w=M[0]*M[0]+M[1]*M[1]+M[2]*M[2],I=w>0?(A[0]*M[0]+A[1]*M[1]+A[2]*M[2])/w:0,E=Math.max(0,Math.min(1,I)),L=[y[0]+E*M[0],y[1]+E*M[1],y[2]+E*M[2]];if(b=Math.max(b,et(tt(h[S],L))),b>g)break}b>g&&(m.push(x),_=x)}}return{curve:i,params:l,points:h,fractions:f,closed:a,length:d,boundarySubset:m}}p(ju,"sampleSharedEdge");function Qu(i){let t=0;for(let e=0;e<i.length;e+=1){let[n,s]=i[e],[r,o]=i[(e+1)%i.length];t+=n*o-r*s}return t/2}p(Qu,"polygonArea");function Wr(i,t,e,n,s){let[r,o,a,c]=e,l=s===0?o-r:c-a;if(l<=0)return 1;let u=4,h=0;for(let d=0;d<=u;d+=1){let m=s===0?a+(c-a)*d/u:r+(o-r)*d/u;for(let g=0;g<u;g+=1){let _=(s===0?r:a)+l*g/u,x=_+l/u,y=(_+x)/2,v=p(w=>s===0?lt(i.surface,t,w,m):lt(i.surface,t,m,w),"at"),b=v(_),S=v(x),A=v(y),M=[(b[0]+S[0])/2,(b[1]+S[1])/2,(b[2]+S[2])/2];h=Math.max(h,et(tt(A,M)))}}if(h<=n)return 1;let f=Math.sqrt(h/n);return Math.min(256,Math.max(1,Math.ceil(u*f)))}p(Wr,"gridStepsForDirection");function th(i,t,e){let n=!1;for(let s of i)for(let r=0;r<s.length;r+=1){let[o,a]=s[r],[c,l]=s[(r+1)%s.length];a>e!=l>e&&t<(c-o)*(e-a)/(l-a)+o&&(n=!n)}return n}p(th,"pointInLoopsEvenOdd");function eh(i,t,e,n,s){let r=i;for(let[o,a,c]of[[0,t,!1],[0,e,!0],[1,n,!1],[1,s,!0]]){let l=r;r=[];for(let u=0;u<l.length;u+=1){let h=l[u],f=l[(u+l.length-1)%l.length],d=c?h[o]<=a:h[o]>=a,m=c?f[o]<=a:f[o]>=a;if(d!==m){let g=(a-f[o])/(h[o]-f[o]);r.push([f[0]+g*(h[0]-f[0]),f[1]+g*(h[1]-f[1])])}d&&r.push(h)}if(r.length<3)return[]}return r}p(eh,"clipPolygonToCell");function $r(i,t,e,n,s=1/0){let r=1/0,o=-1/0,a=1/0,c=-1/0;for(let L of e)for(let[D,R]of L)D<r&&(r=D),D>o&&(o=D),R<a&&(a=R),R>c&&(c=R);if(!(o>r)||!(c>a))return null;let l=[r,o,a,c],u=Math.min(256,Math.max(Wr(i,t,l,n,0),Math.ceil((o-r)/s))),h=Math.min(256,Math.max(Wr(i,t,l,n,1),i.surface.kind==="sphere"?Math.ceil((c-a)/s):1)),f=(o-r)/u,d=(c-a)/h,m=p((L,D)=>[Math.min(u-1,Math.max(0,Math.floor((L-r)/f))),Math.min(h-1,Math.max(0,Math.floor((D-a)/d)))],"cellOf"),g=new Set,_=[],x=new Map;for(let L of e){let D=L.segmentOrds||[],R=L.segmentMeta||[];for(let C=0;C<L.length;C+=1){let[P,T]=L[C],[U,F]=L[(C+1)%L.length],N=_.length;_.push([P,T,U,F,D[C]||0,R[C]||null]);let[O,k]=m(Math.min(P,U),Math.min(T,F)),[z,H]=m(Math.max(P,U),Math.max(T,F));for(let X=O;X<=z;X+=1)for(let B=k;B<=H;B+=1){let W=X*h+B;g.add(W);let q=x.get(W);q||x.set(W,q=[]),q.push(N)}}}let y=[],v=new Map,b=Math.max(Math.abs(r),Math.abs(o),o-r,1e-12)*2**-23,S=Math.max(Math.abs(a),Math.abs(c),c-a,1e-12)*2**-23,A=p((L,D)=>{let R=Math.round((L-r)/f),C=Math.round((D-a)/d),P=R===u?o:r+R*f,T=C===h?c:a+C*d;i.surface.kind!=="plane"&&(Math.abs(L-P)<=b&&(L=P),Math.abs(D-T)<=S&&(D=T));let U=`${L}:${D}`,F=v.get(U);return F===void 0&&(F=y.length,y.push([L,D]),v.set(U,F)),F},"vertexId"),M=[],w=Math.abs((o-r)*(c-a))*1e-12||1e-30,I=[],E=[];for(let L=0;L<=u;L+=1)I.push(L===u?o:r+L*f);for(let L=0;L<=h;L+=1)E.push(L===h?c:a+L*d);for(let L=0;L<u;L+=1)for(let D=0;D<h;D+=1){let R=I[L],C=I[L+1],P=E[D],T=E[D+1];if(!g.has(L*h+D)){if(!th(e,(R+C)/2,(P+T)/2))continue;let B=A(R,P),W=A(C,P),q=A(C,T),$=A(R,T);M.push(B,W,q,B,q,$);continue}let U=e.map(B=>eh(B,R,C,P,T)).filter(B=>B.length>=3);if(!U.length)continue;let F=0,N=0;for(let B=0;B<U.length;B+=1){let W=Math.abs(Qu(U[B]));W>N&&(N=W,F=B)}if(N<=w)continue;let O=U[F].map(([B,W])=>new mt(B,W)),k=U.filter((B,W)=>W!==F).map(B=>B.map(([W,q])=>new mt(W,q))),z;try{z=yn.triangulateShape(O,k)}catch{continue}let H=[...O,...k.flat()],X=H.map(({x:B,y:W})=>A(B,W));for(let[B,W,q]of z){let $=H[B],J=H[W],K=H[q],Q=(J.x-$.x)*(K.y-$.y)-(K.x-$.x)*(J.y-$.y);Math.abs(Q)/2>w&&X[B]!==X[W]&&X[W]!==X[q]&&X[q]!==X[B]&&M.push(X[B],X[W],X[q])}}return{uvVerts:y,triangles:M,vertexIds:v,segmentIndex:{segments:_,segmentsByCell:x,cellOf:m,stepsV:h}}}p($r,"gridTriangulate");function nh(i,t,e,n,s,r){let o=s-e,a=r-n,c=o*o+a*a,l=c>0?((i-e)*o+(t-n)*a)/c:0;l=Math.max(0,Math.min(1,l));let u=e+l*o,h=n+l*a;return{distSq:(i-u)*(i-u)+(t-h)*(t-h),t:l}}p(nh,"projectToSegment");function Xr(i,t,e,n,s,r){let o=s-e,a=r-n,c=o*o+a*a,l=c>0?((i-e)*o+(t-n)*a)/c:0;l=Math.max(0,Math.min(1,l));let u=e+l*o,h=n+l*a;return(i-u)*(i-u)+(t-h)*(t-h)}p(Xr,"pointToSegmentDistanceSq");function ih(i,t,e,n){let s=new Map,r=p((m,g)=>m<g?m*4294967296+g:g*4294967296+m,"keyOf");for(let m=0;m<i.length;m+=3){let[g,_,x]=[i[m],i[m+1],i[m+2]];for(let[y,v]of[[g,_],[_,x],[x,g]]){let b=r(y,v);s.set(b,(s.get(b)||0)+1)}}let{segments:o,segmentsByCell:a,cellOf:c,stepsV:l}=e,u=n*n,h=new Map,f=p((m,g)=>{let _=r(m,g);if(s.get(_)!==1)return 0;let x=h.get(_);if(x!==void 0)return x;x=0;let[y,v]=t[m],[b,S]=t[g],[A,M]=c((y+b)/2,(v+S)/2),w=a.get(A*l+M)||[];for(let I of w){let[E,L,D,R,C]=o[I];if(C&&Xr(y,v,E,L,D,R)<u&&Xr(b,S,E,L,D,R)<u){x=C;break}}return h.set(_,x),x},"ordOfMeshEdge"),d=new Uint32Array(i.length);for(let m=0;m<i.length;m+=3){let[g,_,x]=[i[m],i[m+1],i[m+2]];d[m]=f(_,x),d[m+1]=f(x,g),d[m+2]=f(g,_)}return d}p(ih,"attributeBoundaryEdges");function sh(i,t,e,n={},s=null){let{chordTolerance:r,loopTolerance:o,angleTolerance:a,maxRefineDepth:c}={...Vt,...n},l=o*e,u=i.loops.map(R=>Hr(i,R,t,l,s)).filter(R=>R.length>=3);if(!u.length)return null;let h=0;{let R=1/0,C=-1/0,P=1/0,T=-1/0;for(let F of u)for(let[N,O]of F)N<R&&(R=N),N>C&&(C=N),O<P&&(P=O),O>T&&(T=O);let U=[[R,P],[C,P],[R,T],[C,T],[(R+C)/2,(P+T)/2]].map(([F,N])=>lt(i.surface,t,F,N));for(let F=0;F<U.length;F+=1)for(let N=F+1;N<U.length;N+=1)h=Math.max(h,et(tt(U[F],U[N])))}let f=Math.max(Math.min(e,h*4),1e-9),d=r*f,m=o*f,g=m<l?i.loops.map(R=>Hr(i,R,t,m,s)).filter(R=>R.length>=3):u;if(!g.length)return null;let _=g.length===1&&(An(i.surface,i.uv[2])||An(i.surface,i.uv[3]))&&g[0].every(([R,C])=>R===i.uv[0]||R===i.uv[1]||C===i.uv[2]||C===i.uv[3]),x=$r(i,t,g,_?d/3:d,_?a/Math.SQRT2:1/0);if(!x)return null;let{uvVerts:y,triangles:v,vertexIds:b,segmentIndex:S}=x,A=v;if(!A.length)return null;let M=y.map(([R,C])=>lt(i.surface,t,R,C));if(_){let R=new Map,C=new Map;for(let T=0;T<y.length;T+=1){if(!An(i.surface,y[T][1]))continue;let U=y[T][1];R.has(U)?C.set(T,R.get(U)):R.set(U,T)}let P=[];for(let T=0;T<A.length;T+=3){let[U,F,N]=A.slice(T,T+3).map(O=>C.get(O)??O);et(tt(M[U],M[F]))<=e*1e-12||et(tt(M[F],M[N]))<=e*1e-12||et(tt(M[N],M[U]))<=e*1e-12||P.push(U,F,N)}A=P}let w=p(([R,C])=>Sn(i.surface,t,R,C,i.uv,!1),"vertexNormal"),I=y.map(w),E=Math.cos(a),L=p((R,C)=>R<C?`${R}_${C}`:`${C}_${R}`,"edgeKey");for(let R=0;R<(_?0:c);R+=1){let C=new Set,P=new Map,T=p((O,k)=>{let z=L(O,k),H=P.get(z);if(H===void 0){let X=(y[O][0]+y[k][0])/2,B=(y[O][1]+y[k][1])/2,W=lt(i.surface,t,X,B),q=[(M[O][0]+M[k][0])/2,(M[O][1]+M[k][1])/2,(M[O][2]+M[k][2])/2];H=et(tt(W,q))>d||I[O][0]*I[k][0]+I[O][1]*I[k][1]+I[O][2]*I[k][2]<E,P.set(z,H)}return H},"edgeChordBad");for(let O=0;O<A.length;O+=3){let k=A[O],z=A[O+1],H=A[O+2],X=!1;for(let[Rt,ft]of[[k,z],[z,H],[H,k]])T(Rt,ft)&&(C.add(L(Rt,ft)),X=!0);if(X)continue;let B=(y[k][0]+y[z][0]+y[H][0])/3,W=(y[k][1]+y[z][1]+y[H][1])/3,q=lt(i.surface,t,B,W),$=[(M[k][0]+M[z][0]+M[H][0])/3,(M[k][1]+M[z][1]+M[H][1])/3,(M[k][2]+M[z][2]+M[H][2])/3],J=tt(M[z],M[k]),K=tt(M[H],M[k]),Q=[J[1]*K[2]-J[2]*K[1],J[2]*K[0]-J[0]*K[2],J[0]*K[1]-J[1]*K[0]],nt=et(Q),yt=I[k];if(nt>1e-30&&Math.abs((Q[0]*yt[0]+Q[1]*yt[1]+Q[2]*yt[2])/nt)<E||et(tt(q,$))>d){let Rt=[k,z],ft=-1;for(let[ie,At]of[[k,z],[z,H],[H,k]]){let xe=y[ie][0]-y[At][0],Wt=y[ie][1]-y[At][1],It=xe*xe+Wt*Wt;It>ft&&(ft=It,Rt=[ie,At])}C.add(L(Rt[0],Rt[1]))}}if(!C.size)break;let U=new Map,F=p((O,k)=>{let z=L(O,k);if(!C.has(z))return-1;let H=U.get(z);if(H===void 0){let X=(y[O][0]+y[k][0])/2,B=(y[O][1]+y[k][1])/2;H=y.length,y.push([X,B]),M.push(lt(i.surface,t,X,B)),I.push(w([X,B])),U.set(z,H)}return H},"midpointOf"),N=[];for(let O=0;O<A.length;O+=3){let k=A[O],z=A[O+1],H=A[O+2],X=F(k,z),B=F(z,H),W=F(H,k),q=(X>=0)+(B>=0)+(W>=0);if(q===0){N.push(k,z,H);continue}if(q===3)N.push(k,X,W,X,z,B,W,B,H,X,B,W);else if(q===2){let[$,J,K,Q,nt]=X>=0&&B>=0?[k,z,H,X,B]:B>=0&&W>=0?[z,H,k,B,W]:[H,k,z,W,X];N.push($,Q,nt,$,nt,K,Q,J,nt)}else{let[$,J,K,Q]=X>=0?[k,z,H,X]:B>=0?[z,H,k,B]:[H,k,z,W];N.push($,Q,K,Q,J,K)}}A=N}let D=new Map;if(s){let R=0,C=0;for(let[O,k]of y)R=Math.max(R,Math.abs(O)),C=Math.max(C,Math.abs(k));let P=Math.max(R,C,1)*1e-7,{segments:T,segmentsByCell:U,cellOf:F,stepsV:N}=S;for(let O=0;O<y.length;O+=1){let[k,z]=y[O],[H,X]=F(k,z),B=U.get(H*N+X);if(!B)continue;let W=new Map;for(let J of B){let[K,Q,nt,yt,Jt,Rt]=T[J];if(!Rt)continue;let ft=nh(k,z,K,Q,nt,yt);if(ft.distSq>=P*P){let xe=P*P*16,Wt=(k-K)*(k-K)+(z-Q)*(z-Q),It=(k-nt)*(k-nt)+(z-yt)*(z-yt);if(Wt<xe)ft={distSq:Wt,t:0};else if(It<xe)ft={distSq:It,t:1};else continue}let ie=W.get(Jt);if(ie&&ie.distSq<=ft.distSq)continue;let At=ft.t<1e-9?0:ft.t>1-1e-9?1:ft.t;W.set(Jt,{distSq:ft.distSq,f:Rt.f0+At*(Rt.f1-Rt.f0)})}if(!W.size)continue;let q=[],$=null;for(let[J,{distSq:K,f:Q}]of W){let nt=s.get(J);if(!nt)continue;let yt=nt.closed&&Q>=1-1e-12?0:Q;q.push({ord:J,f:yt}),(!$||K<$.distSq)&&($={distSq:K,ord:J,f:yt,shared:nt})}q.length&&(q.sort((J,K)=>J.ord===$.ord&&J.f===$.f?-1:K.ord===$.ord&&K.f===$.f?1:0),D.set(O,q),M[O]=li($.shared,$.f,t))}}return{uvVerts:y,xyz:M,nrm:I,triangles:A,segmentIndex:S,boundary:D,loops:g,singularGrid:_}}p(sh,"tessellateFaceRaw");function rh(i,t,e,n={}){if(t.singularGrid)return;let{chordTolerance:s,angleTolerance:r,maxRefineDepth:o}={...Vt,...n},{uvVerts:a,xyz:c,nrm:l,boundary:u}=t,h=t.mintedVerts;if(!h?.size)return;let f=t.triangles,d=0;for(let v of c)d=Math.max(d,et(tt(v,c[0])));let m=s*Math.max(d,1e-9),g=p(([v,b])=>Sn(i.surface,e,v,b,i.uv,!1),"vertexNormal"),_=Math.cos(r),x=p((v,b)=>v<b?`${v}_${b}`:`${b}_${v}`,"edgeKey"),y=Math.min(3,o);for(let v=0;v<y;v+=1){let b=new Set;for(let w=0;w<f.length;w+=3){let[I,E,L]=[f[w],f[w+1],f[w+2]];if(!(!h.has(I)&&!h.has(E)&&!h.has(L)))for(let[D,R]of[[I,E],[E,L],[L,I]]){if(u.has(D)&&u.has(R))continue;let C=(a[D][0]+a[R][0])/2,P=(a[D][1]+a[R][1])/2,T=lt(i.surface,e,C,P);if(!T||!Number.isFinite(T[0]))continue;let U=[(c[D][0]+c[R][0])/2,(c[D][1]+c[R][1])/2,(c[D][2]+c[R][2])/2];et(tt(T,U))>m&&b.add(x(D,R))}}if(!b.size)break;let S=new Map,A=p((w,I)=>{let E=x(w,I);if(!b.has(E))return-1;let L=S.get(E);if(L===void 0){let D=(a[w][0]+a[I][0])/2,R=(a[w][1]+a[I][1])/2;L=a.length,a.push([D,R]),c.push(lt(i.surface,e,D,R)),l.push(g([D,R])),S.set(E,L)}return L},"midpointOf"),M=[];for(let w=0;w<f.length;w+=3){let I=f[w],E=f[w+1],L=f[w+2],D=A(I,E),R=A(E,L),C=A(L,I),P=(D>=0)+(R>=0)+(C>=0);if(P===0)M.push(I,E,L);else if(P===3)M.push(I,D,C,D,E,R,C,R,L,D,R,C);else if(P===2){let[T,U,F,N,O]=D>=0&&R>=0?[I,E,L,D,R]:R>=0&&C>=0?[E,L,I,R,C]:[L,I,E,C,D];M.push(T,N,O,T,O,F,N,U,O)}else{let[T,U,F,N]=D>=0?[I,E,L,D]:R>=0?[E,L,I,R]:[L,I,E,C];M.push(T,N,F,N,U,F)}}f=M}t.triangles=f}p(rh,"refineInteriorPostConform");function oh(i,t){let{uvVerts:e,xyz:n,nrm:s,triangles:r,segmentIndex:o}=t,a=new Float32Array(n.length*3),c=new Float32Array(n.length*3),l=i.reversed?-1:1;for(let m=0;m<n.length;m+=1)a.set(n[m],m*3),c[m*3]=s[m][0]*l,c[m*3+1]=s[m][1]*l,c[m*3+2]=s[m][2]*l;let u=i.reversed?ch(r):Uint32Array.from(r),h=0,f=0;for(let[m,g]of e)h=Math.max(h,Math.abs(m)),f=Math.max(f,Math.abs(g));let d=ih(u,e,o,Math.max(h,f,1)*1e-7);return{positions:a,normals:c,indices:u,sideOrds:d,uv:e}}p(oh,"finalizeFaceMesh");function ah(i,t,e,n=0){let s=p(u=>{let h=t.get(u),f=h?.length?n*.5/h.length:0;return Math.min(.25,Math.max(1e-9,f))},"fractionEps"),r=1e-9,o=p((u,h)=>{let f=t.get(u),d=s(u);return h<=d?0:h>=1-d?f?.closed?0:1:h},"canonicalFraction"),a=new Map,c=p((u,h)=>{let f=a.get(u);f||a.set(u,f=[]),f.push(o(u,h))},"addFraction");for(let{raw:u}of i)for(let h of u.boundary.values())for(let{ord:f,f:d}of h)c(f,d);for(let[u,h]of a){let f=s(u);h.sort((g,_)=>g-_);let d=[];for(let g of h)(!d.length||g-d[d.length-1]>f)&&d.push(g);t.get(u)?.closed&&d.length>1&&1-d[d.length-1]<=f&&d.pop(),a.set(u,d)}let l=p((u,h)=>{let f=a.get(u);if(!f)return h;let d=0,m=f.length-1;for(;d<m;){let _=d+m>>1;f[_]<h?d=_+1:m=_}let g=[f[d],f[d-1]??f[d]];return Math.abs(g[0]-h)<=Math.abs(g[1]-h)?g[0]:g[1]},"representativeOf");for(let{face:u,raw:h}of i){if(u.surface.kind==="plane"){let{origin:x,xdir:y,ydir:v}=u.surface,b=new Map,S=h.loops.map(M=>{let w=[];w.segmentOrds=[],w.segmentMeta=[];for(let I=0;I<M.length;I+=1){let E=M.segmentMeta[I],L=E&&t.get(E.ord);if(!L){w.push(M[I]),w.segmentOrds.push(M.segmentOrds[I]),w.segmentMeta.push(null);continue}let D=p(N=>l(E.ord,o(E.ord,N)),"canonical"),R=p((N,O)=>L.closed&&N===0&&O>.5?1:N,"unwrap"),C=R(D(E.f0),E.f0),P=R(D(E.f1),E.f1),T=s(E.ord),U=a.get(E.ord).filter(N=>N>Math.min(C,P)+T&&N<Math.max(C,P)-T);P<C&&U.reverse();let F=[C,...U,P];for(let N=0;N<F.length;N+=1){if(N+1<F.length&&Math.abs(F[N+1]-F[N])<=T)continue;let O=o(E.ord,F[N]),k=li(L,O,e),z=tt(k,x),H=[z[0]*y[0]+z[1]*y[1]+z[2]*y[2],z[0]*v[0]+z[1]*v[1]+z[2]*v[2]];N+1<F.length&&(w.push(H),w.segmentOrds.push(E.ord),w.segmentMeta.push({ord:E.ord,f0:F[N],f1:F[N+1]}));let X=`${H[0]}:${H[1]}`,B=b.get(X);B?B.labels.push({ord:E.ord,f:O}):b.set(X,{xyz:k,labels:[{ord:E.ord,f:O}]})}}return w}),A=$r(u,e,S,1/0);A?.triangles.length&&(Object.assign(h,A,{boundary:new Map,loops:S}),h.xyz=A.uvVerts.map(([M,w],I)=>{let E=b.get(`${M}:${w}`);return E&&h.boundary.set(I,E.labels),E?.xyz??lt(u.surface,e,M,w)}),h.nrm=A.uvVerts.map(([M,w])=>Sn(u.surface,e,M,w,u.uv,!1)))}for(let[x,y]of h.boundary){for(let S of y)S.f=l(S.ord,o(S.ord,S.f));y.sort((S,A)=>S.ord-A.ord||S.f-A.f);let v=y[0],b=t.get(v.ord);b&&(h.xyz[x]=li(b,v.f,e))}let f=0;for(let[x,y]of h.uvVerts)f=Math.max(f,Math.abs(x),Math.abs(y));let d=Math.max(f,1)*.01,m=p((x,y)=>Math.abs(h.uvVerts[x][0]-h.uvVerts[y][0])<=d&&Math.abs(h.uvVerts[x][1]-h.uvVerts[y][1])<=d,"uvClose"),g=new Map,_=new Map;for(let x of h.boundary.keys()){let y=h.xyz[x],v=`${y[0]}:${y[1]}:${y[2]}`,b=g.get(v);if(b===void 0){g.set(v,[x]);continue}let S=b.find(A=>m(A,x));S!==void 0?_.set(x,S):b.push(x)}if(_.size){let x=[];for(let y=0;y<h.triangles.length;y+=3){let v=_.get(h.triangles[y])??h.triangles[y],b=_.get(h.triangles[y+1])??h.triangles[y+1],S=_.get(h.triangles[y+2])??h.triangles[y+2];v!==b&&b!==S&&S!==v&&x.push(v,b,S)}h.triangles=x;for(let y of _.keys())h.boundary.delete(y)}}for(let{face:u,raw:h}of i){let{uvVerts:f,xyz:d,nrm:m,boundary:g}=h;if(!g.size)continue;let _=new Map,x=p((C,P)=>C<P?C*4294967296+P:P*4294967296+C,"pairKey");for(let C=0;C<h.triangles.length;C+=3){let[P,T,U]=[h.triangles[C],h.triangles[C+1],h.triangles[C+2]];for(let[F,N]of[[P,T],[T,U],[U,P]]){let O=x(F,N);_.set(O,(_.get(O)||0)+1)}}let y=p(([C,P])=>Sn(u.surface,e,C,P,u.uv,!1),"vertexNormal"),v=new Map,b=p((C,P,T,U,F)=>{let N=`${C}:${P.toFixed(12)}:${Math.min(T,U)}:${Math.max(T,U)}`,O=v.get(N);if(O!==void 0)return O;let k=[An(u.surface,f[T][1])?f[U][0]:An(u.surface,f[U][1])?f[T][0]:f[T][0]+F*(f[U][0]-f[T][0]),f[T][1]+F*(f[U][1]-f[T][1])];O=f.length,f.push(k);let z=li(t.get(C),P,e);return d.push(z),m.push(y(k)),g.set(O,[{ord:C,f:P}]),(h.mintedVerts??=new Set).add(O),v.set(N,O),O},"vertexAt"),S=p((C,P)=>{let T=g.get(C),U=g.get(P);if(!T||!U||_.get(x(C,P))!==1)return null;let F=null,N=null;for(let X of T){let B=U.find(W=>W.ord===X.ord);if(B){F=X,N=B;break}}if(!F||!N)return null;let O=a.get(F.ord);if(!O)return null;let k=t.get(F.ord),z=s(F.ord),H=[];if(k?.closed){let X=(N.f-F.f+1)%1,B=X<=.5,W=B?F.f:N.f,q=B?X:(F.f-N.f+1)%1;if(q<=z*2)return null;for(let $ of O){let J=($-W+1)%1;J>z&&J<q-z&&H.push({f:$,s:B?J/q:1-J/q})}}else{let X=Math.min(F.f,N.f),B=Math.max(F.f,N.f);if(B-X<=z*2)return null;for(let W of O)W>X+z&&W<B-z&&H.push({f:W,s:(W-F.f)/(N.f-F.f)})}return H.length?(H.sort((X,B)=>X.s-B.s),{ord:F.ord,between:H}):null},"insertsFor"),A=[],M=p((C,P,T,U)=>{if(U>24){A.push(C,P,T);return}for(let[F,N,O]of[[C,P,T],[P,T,C],[T,C,P]]){let k=S(F,N);if(k){let z=F;for(let{f:H,s:X}of k.between){let B=b(k.ord,H,F,N,X);M(z,B,O,U+1),z=B}M(z,N,O,U+1);return}}A.push(C,P,T)},"emit"),w=h.triangles;for(let C=0;C<w.length;C+=3)M(w[C],w[C+1],w[C+2],0);h.triangles=A;let I=0;for(let[C,P]of f)I=Math.max(I,Math.abs(C),Math.abs(P));let E=Math.max(I,1)*.01,L=p((C,P)=>Math.abs(f[C][0]-f[P][0])<=E&&Math.abs(f[C][1]-f[P][1])<=E,"uvCloseAfter"),D=new Map,R=new Map;for(let C of g.keys()){let P=d[C],T=`${P[0]}:${P[1]}:${P[2]}`,U=D.get(T);if(U===void 0){D.set(T,[C]);continue}let F=U.find(N=>L(N,C));F!==void 0?R.set(C,F):U.push(C)}if(R.size){let C=[];for(let P=0;P<h.triangles.length;P+=3){let T=R.get(h.triangles[P])??h.triangles[P],U=R.get(h.triangles[P+1])??h.triangles[P+1],F=R.get(h.triangles[P+2])??h.triangles[P+2];T!==U&&U!==F&&F!==T&&C.push(T,U,F)}h.triangles=C;for(let[P,T]of R){let U=g.get(P),F=g.get(T);if(U&&F)for(let N of U)F.some(O=>O.ord===N.ord&&O.f===N.f)||F.push(N);g.delete(P)}}}}p(ah,"conformBoundaries");function ch(i){let t=new Uint32Array(i.length);for(let e=0;e<i.length;e+=3)t[e]=i[e],t[e+1]=i[e+2],t[e+2]=i[e+1];return t}p(ch,"flipWinding");function bs(i,t,e={}){let n=[1/0,1/0,1/0],s=[-1/0,-1/0,-1/0],r=[],o=0,a=0;for(let A of i.faces)for(let M of A.loops)for(let w of M)for(let I of[w.range[0],(w.range[0]+w.range[1])/2,w.range[1]]){let[E,L]=bn(w,t,I),D=lt(A.surface,t,E,L);for(let R=0;R<3;R+=1)D[R]<n[R]&&(n[R]=D[R]),D[R]>s[R]&&(s[R]=D[R])}let c=Math.max(et(tt(s,n)),1e-6),{chordTolerance:l}={...Vt,...e},u=new Map;for(let A of i.edges)A.curve&&u.set(A.ord,ju(A.curve,t,l*c));{let A=c*476837158203125e-21,M=[],w=p(I=>{for(let E of M)if(et(tt(E,I))<=A)return E;return M.push(I),I},"canonicalCorner");for(let I of u.values()){if(I.closed){let E=w(I.points[0]);I.points[0]=E,I.points[I.points.length-1]=E;continue}I.points[0]=w(I.points[0]),I.points[I.points.length-1]=w(I.points[I.points.length-1])}}let h=[];for(let A of i.faces){let M=sh(A,t,c,e,e.noSharedBoundaries?null:u);M&&h.push({face:A,raw:M})}if(!e.noSharedBoundaries&&!e.noConformPass){ah(h,u,t,l*c);for(let{face:A,raw:M}of h)rh(A,M,t,e)}let f=e.collectBoundaryDebug?[]:null;for(let{face:A,raw:M}of h){f&&f.push({faceOrd:A.ord,reversed:!!A.reversed,xyz:M.xyz,triangles:M.triangles.slice(),boundaryByVert:new Map(M.boundary)});let w=oh(A,M);w&&(r.push({ord:A.ord,color:A.color??null,mesh:w}),o+=w.positions.length/3,a+=w.indices.length)}let d=new Float32Array(o*3),m=new Float32Array(o*3),g=new Float32Array(o),_=new Uint32Array(a),x=new Uint32Array(a),y=[],v=0,b=0;for(let{ord:A,color:M,mesh:w}of r){d.set(w.positions,v*3),m.set(w.normals,v*3),g.fill(A,v,v+w.positions.length/3);for(let I=0;I<w.indices.length;I+=1)_[b+I]=w.indices[I]+v;w.sideOrds&&x.set(w.sideOrds,b),y.push({ord:A,color:M,indexStart:b,indexCount:w.indices.length}),v+=w.positions.length/3,b+=w.indices.length}n=[1/0,1/0,1/0],s=[-1/0,-1/0,-1/0];for(let A=0;A<d.length;A+=3)for(let M=0;M<3;M+=1){let w=d[A+M];w<n[M]&&(n[M]=w),w>s[M]&&(s[M]=w)}let S=[];for(let A of i.edges){let M=u.get(A.ord);if(!M)continue;let w=new Float32Array(M.points.length*3);for(let I=0;I<M.points.length;I+=1)w.set(M.points[I],I*3);S.push({ord:A.ord,visibilityClass:A.class,polyline:w})}return{positions:d,normals:m,faceOrds:g,indices:_,sideOrds:x,faceRanges:y,edges:S,bounds:{min:n,max:s},scale:c,...f?{boundaryDebug:f,sharedEdges:u}:{}}}p(bs,"tessellateComponent");var Kr=1397966164,te=4,hi=1,jr=16*1024,Qr=4*1024*1024,lh=/^[0-9a-f]{64}$/,Yr=new Set(["chordTolerance","chordToleranceF64","angleTolerance","angleToleranceF64"]),to=new Set(["none","feature","tangent","seam","degenerate","boundary","nonManifold","unknown"]);function Zt(i,t){let e=typeof i=="string"?i:"";if(!lh.test(e))throw new TypeError(`${t} must be 64 lowercase hex characters`);return e}p(Zt,"requireDigest");function Zr(i){if(typeof i!="number"||!Number.isFinite(i)||i<=0)throw new TypeError("tessellation tolerances must be positive finite binary64 values");let t=new Uint8Array(8);return new DataView(t.buffer).setFloat64(0,i,!1),[...t].map(e=>e.toString(16).padStart(2,"0")).join("")}p(Zr,"float64Hex");function fi(i={}){let t={...Vt,...i},e=t.chordTolerance,n=t.angleTolerance;return Object.freeze({chordTolerance:e,chordToleranceF64:Zr(e),angleTolerance:n,angleToleranceF64:Zr(n)})}p(fi,"tessellationQuality");function Ae(i,t={}){let e=Zt(i,"surfaceInput"),n=fi(t);return`${e}-t${pe}-p${te}-l${n.chordToleranceF64}-a${n.angleToleranceF64}`}p(Ae,"tessellationCacheKey");function eo(i,t,e={}){return`${Ae(i,e)}-s${Zt(t,"surfaceObject")}`}p(eo,"resolvedTessellationIdentity");function uh(i){return i+3&-4}p(uh,"align4");function Ss(i){return i!==null&&typeof i=="object"&&!Array.isArray(i)}p(Ss,"isObject");function ui(i,t){return Array.isArray(i)&&i.length===t&&i.every(e=>typeof e=="number"&&Number.isFinite(e))}p(ui,"finiteTuple");function As(i){return Number.isSafeInteger(i)&&i>0}p(As,"validOrdinal");function hh(i){if(!Array.isArray(i))return null;let t=new Map;for(let e of i){if(!Array.isArray(e)||e.length!==2||!As(e[0])||!to.has(e[1])||t.has(e[0]))return null;t.set(e[0],e[1])}return t}p(hh,"edgeClassMap");function no(i){if(!Ss(i?.bounds)||!ui(i.bounds.min,3)||!ui(i.bounds.max,3)||i.bounds.min.some((r,o)=>r>i.bounds.max[o])||typeof i.scale!="number"||!Number.isFinite(i.scale)||i.scale<=0||i.partColor!=null&&!ui(i.partColor,4)||!Array.isArray(i.faceRanges)||!Array.isArray(i.edges))return!1;let t=new Set,e=0;for(let r of i.faceRanges)if(!Ss(r)||!As(r.ord)||t.has(r.ord)||!qe(r.indexStart)||!qe(r.indexCount)||r.indexStart%3!==0||r.indexCount%3!==0||r.indexStart!==e||r.color!=null&&!ui(r.color,4)||(t.add(r.ord),e+=r.indexCount,!Number.isSafeInteger(e)))return!1;if(e!==i.indexCount)return!1;let n=hh(i.edgeClasses);if(!n)return!1;let s=new Set;for(let r of i.edges){if(!Ss(r)||!As(r.ord)||s.has(r.ord)||!qe(r.count)||r.count%3!==0||r.visibilityClass!=null&&!to.has(r.visibilityClass)||!n.has(r.ord)||r.visibilityClass!=null&&n.get(r.ord)!==r.visibilityClass)return!1;s.add(r.ord)}return!0}p(no,"validRenderingMetadata");function io(i){return(Array.isArray(i?.edges)?i.edges:[]).map(e=>[e.ord,String(e.class??"none")])}p(io,"edgeClassesFromSurfIndex");function so(i,{partColor:t=null,edgeClasses:e=null,surfaceInput:n,surfaceObject:s,tessellation:r={}}={}){let o=Array.isArray(i.edges)?i.edges:[];if(!Array.isArray(i.faceRanges)||!Array.isArray(e))throw new TypeError("TESS v4 requires complete faceRanges and edgeClasses metadata");let a=fi(r),c=Ae(n,r),l=Zt(s,"surfaceObject"),u={tessellationInput:c,surfaceInput:Zt(n,"surfaceInput"),surfaceDigest:l,quality:a,tessellatorVersion:pe,payloadVersion:te,partColor:t??null,edgeClasses:e,faceRanges:i.faceRanges,bounds:{min:[...i.bounds.min],max:[...i.bounds.max]},scale:i.scale,positionCount:i.positions.length,normalCount:i.normals.length,faceOrdCount:i.faceOrds.length,indexCount:i.indices.length,sideOrdCount:i.sideOrds.length,edges:o.map(v=>({ord:v.ord,visibilityClass:v.visibilityClass??null,count:v.polyline.length}))};if(!no(u))throw new TypeError("TESS v4 requires valid complete rendering metadata");let h=JSON.stringify(u),f=new TextEncoder().encode(h),d=uh(f.length),m=i.positions.length+i.normals.length+i.faceOrds.length+i.indices.length+i.sideOrds.length+o.reduce((v,b)=>v+b.polyline.length,0),g=new Uint8Array(12+d+m*4),_=new DataView(g.buffer);_.setUint32(0,Kr,!0),_.setUint32(4,te,!0),_.setUint32(8,d,!0),g.set(f,12),g.fill(32,12+f.length,12+d);let x=12+d,y=p((v,b)=>{new b(g.buffer,x,v.length).set(v),x+=v.length*4},"append");y(i.positions,Float32Array),y(i.normals,Float32Array),y(i.faceOrds,Float32Array),y(i.indices,Uint32Array),y(i.sideOrds,Uint32Array);for(let v of o)y(v.polyline,Float32Array);return g}p(so,"encodeComponentTessellation");function qe(i){return Number.isSafeInteger(i)&&i>=0}p(qe,"validCount");function ro({headerBytes:i,arrayBytes:t,faceRangeCount:e,edgeCount:n,edgeClassCount:s,edgeSegmentCount:r}){if(![i,t,e,n,s,r].every(qe)||i<=0||i>Qr||i%4!==0||t%4!==0)throw new TypeError("invalid tessellation size facts");let a=t+8*r+8*i+256*(e+n+s);if(!Number.isSafeInteger(a))throw new TypeError("tessellation decoded size exceeds the safe integer range");return a}p(ro,"tessellationDecodedBytes");function fh(i,t={}){try{if(i?.tessellatorVersion!==pe||i?.payloadVersion!==te)return null;let e=Zt(i.surfaceInput,"surfaceInput"),n=Zt(i.surfaceDigest,"surfaceDigest"),s=i.quality;if(!s||typeof s!="object"||Array.isArray(s)||Object.keys(s).length!==Yr.size||Object.keys(s).some(l=>!Yr.has(l)))return null;let r=fi({chordTolerance:s.chordTolerance,angleTolerance:s.angleTolerance});if(s.chordToleranceF64!==r.chordToleranceF64||s.angleToleranceF64!==r.angleToleranceF64)return null;let o=Ae(e,r);if(i.tessellationInput!==o)return null;let a=eo(e,n,r);if(t.surfaceInput!==void 0&&Zt(t.surfaceInput,"expected surfaceInput")!==e)return null;let c=t.surfaceObject??t.surfaceDigest;return c!==void 0&&Zt(c,"expected surfaceObject")!==n||t.tessellationInput!==void 0&&String(t.tessellationInput)!==o||t.renderIdentity!==void 0&&String(t.renderIdentity)!==a||t.tessellation!==void 0&&Ae(e,t.tessellation)!==o?null:Object.freeze({surfaceInput:e,surfaceObject:n,tessellationInput:o,renderIdentity:a,quality:r,tessellatorVersion:pe,payloadVersion:te})}catch{return null}}p(fh,"decodedIdentity");function oo(i,t={}){if(!(i instanceof Uint8Array)||i.length<12)return null;let e=new DataView(i.buffer,i.byteOffset,i.byteLength);if(e.getUint32(0,!0)!==Kr||e.getUint32(4,!0)!==te)return null;let n=e.getUint32(8,!0);if(n===0||n>Qr||n%4!==0||12+n>i.length)return null;let s=JSON.parse(new TextDecoder().decode(i.subarray(12,12+n))),r=fh(s,t);if(!r||!Array.isArray(s.edges)||!Array.isArray(s.faceRanges)||!Array.isArray(s.edgeClasses))return null;let o=[s.positionCount,s.normalCount,s.faceOrdCount,s.indexCount,s.sideOrdCount],a=s.edges.map(d=>d?.count),c=[...o,...a];if(!c.every(qe)||s.positionCount%3!==0||s.normalCount!==s.positionCount||s.faceOrdCount*3!==s.positionCount||s.indexCount%3!==0||s.sideOrdCount!==s.indexCount||a.some(d=>d%3!==0)||!no(s))return null;let l=c.reduce((d,m)=>d+m,0);if(!Number.isSafeInteger(l)||l>Number.MAX_SAFE_INTEGER/4)return null;let u=l*4;if(i.length!==12+n+u)return null;let h=Object.freeze({headerBytes:n,arrayBytes:u,faceRangeCount:s.faceRanges.length,edgeCount:s.edges.length,edgeClassCount:s.edgeClasses.length,edgeSegmentCount:a.reduce((d,m)=>d+Math.max(0,m/3-1),0)}),f=ro(h);return{header:s,identity:r,sizes:h,decodedBytes:f}}p(oo,"decodeEnvelope");function ws(i,t={}){try{let e=oo(i,t);if(!e)return null;let n=Object.freeze({byteLength:i.byteLength,decodedBytes:e.decodedBytes,surfaceInput:e.identity.surfaceInput,surfaceObject:e.identity.surfaceObject,tessellationInput:e.identity.tessellationInput,renderIdentity:e.identity.renderIdentity,quality:e.identity.quality,tessellatorVersion:pe,payloadVersion:te,...e.sizes});for(let s of["byteLength","decodedBytes","surfaceInput","surfaceObject","tessellationInput","renderIdentity","tessellatorVersion","payloadVersion","headerBytes","arrayBytes","faceRangeCount","edgeCount","edgeClassCount","edgeSegmentCount"])if(t[s]!==void 0&&t[s]!==n[s])return null;return n}catch{return null}}p(ws,"tessellationPayloadFacts");var Jr=new Set(["schemaVersion","object","byteLength","decodedBytes","surfaceInput","surfaceObject","tessellationInput","renderIdentity","quality","tessellatorVersion","payloadVersion","headerBytes","arrayBytes","faceRangeCount","edgeCount","edgeClassCount","edgeSegmentCount"]);function Ts(i,t={}){try{if(!i||typeof i!="object"||Array.isArray(i)||Object.keys(i).length!==Jr.size||Object.keys(i).some(l=>!Jr.has(l))||i.schemaVersion!==hi||i.tessellatorVersion!==pe||i.payloadVersion!==te)return null;let e=Zt(i.surfaceInput,"surfaceInput"),n=Zt(i.surfaceObject,"surfaceObject"),s=Zt(i.object,"object"),r=fi({chordTolerance:i.quality?.chordTolerance,angleTolerance:i.quality?.angleTolerance});if(i.quality?.chordToleranceF64!==r.chordToleranceF64||i.quality?.angleToleranceF64!==r.angleToleranceF64)return null;let o=Ae(e,r),a=eo(e,n,r);if(i.tessellationInput!==o||i.renderIdentity!==a)return null;let c={headerBytes:i.headerBytes,arrayBytes:i.arrayBytes,faceRangeCount:i.faceRangeCount,edgeCount:i.edgeCount,edgeClassCount:i.edgeClassCount,edgeSegmentCount:i.edgeSegmentCount};return!qe(i.byteLength)||i.byteLength<=0||i.byteLength!==12+i.headerBytes+i.arrayBytes||i.decodedBytes!==ro(c)||t.tessellationInput!==void 0&&t.tessellationInput!==o||t.object!==void 0&&t.object!==s||t.surfaceInput!==void 0&&t.surfaceInput!==e||t.surfaceObject!==void 0&&t.surfaceObject!==n?null:Object.freeze({schemaVersion:hi,object:s,byteLength:i.byteLength,decodedBytes:i.decodedBytes,surfaceInput:e,surfaceObject:n,tessellationInput:o,renderIdentity:a,quality:r,tessellatorVersion:pe,payloadVersion:te,...c})}catch{return null}}p(Ts,"validateTessellationProbeRow");function ao(i,t={}){try{let e=oo(i,t);if(!e)return null;let{header:n,identity:s}=e,r=i.byteOffset+12+e.sizes.headerBytes,o=r%4===0,a=p((m,g)=>{let _=o?new g(i.buffer,r,m):new g(i.buffer.slice(r,r+m*4));return r+=m*4,_},"take"),c=a(n.positionCount,Float32Array),l=a(n.normalCount,Float32Array),u=a(n.faceOrdCount,Float32Array),h=a(n.indexCount,Uint32Array),f=a(n.sideOrdCount,Uint32Array),d=n.edges.map(m=>({ord:m.ord,visibilityClass:m.visibilityClass,polyline:a(m.count,Float32Array)}));return{component:{positions:c,normals:l,faceOrds:u,indices:h,sideOrds:f,faceRanges:n.faceRanges,edges:d,bounds:n.bounds,scale:n.scale},partColor:n.partColor??null,edgeClasses:Array.isArray(n.edgeClasses)?n.edgeClasses:null,identity:s}}catch{return null}}p(ao,"decodeComponentTessellation");var $_=32*1024*1024;import{createHash as dh,randomUUID as ph}from"node:crypto";import Tt from"node:fs";import co from"node:os";import Gt from"node:path";var Es=class extends Error{static{p(this,"TessellationMeshConflictError")}constructor(t="tessellation producer returned different bytes for the same immutable input"){super(t),this.name="TessellationMeshConflictError"}};function lo(i=process.env){return i.CADGEN_MESH_CACHE!=="0"}p(lo,"tessellationCacheEnabled");function uo(i=process.env){let t=(i.CADGEN_CACHE_DIR||"").trim();if(t){let e=t.replace(/^~(?=$|[/\\])/,co.homedir()),n=Gt.resolve(e);return Gt.isAbsolute(e)||(i.CADGEN_CACHE_DIR=n),n}if(process.platform==="win32"){let e=(i.LOCALAPPDATA||"").trim();if(e)return Gt.join(e,"cadgen")}else{let e=(i.XDG_CACHE_HOME||"").trim();if(e)return Gt.join(e,"cadgen")}return Gt.join(co.homedir(),".cache","cadgen")}p(uo,"cadgenCacheRootDir");function mh(i=process.env){return Gt.join(uo(i),"index","mesh")}p(mh,"tessellationCacheDir");function di(i){return dh("sha256").update(i).digest("hex")}p(di,"digestBytes");function Rs(i,t=process.env){return Gt.join(uo(t),"objects",i.slice(0,2),i.slice(2))}p(Rs,"objectPath");function ho(i,t=process.env){return Gt.join(mh(t),i)}p(ho,"indexPath");function gh(i){return Gt.join(Gt.dirname(i),`.${Gt.basename(i)}.${process.pid}.${ph()}.tmp`)}p(gh,"tempPath");function fo(i,t){Tt.mkdirSync(Gt.dirname(i),{recursive:!0});let e=gh(i);try{Tt.writeFileSync(e,t,{flag:"wx"}),Tt.renameSync(e,i)}finally{try{Tt.unlinkSync(e)}catch{}}}p(fo,"writeAtomic");function xh(i){let t=Tt.openSync(i,"r");try{let e=Tt.fstatSync(t);if(!e.isFile()||e.size<=0||e.size>jr)return null;let n=Buffer.allocUnsafe(e.size);return Tt.readSync(t,n,0,n.length,0)!==n.length?null:JSON.parse(n.toString("utf8"))}finally{Tt.closeSync(t)}}p(xh,"readBoundedJson");function po(i,t=process.env){if(!lo(t))return null;try{let e=Ts(xh(ho(i,t)),{tessellationInput:i});if(!e)return null;let n=Tt.statSync(Rs(e.object,t));return n.isFile()&&n.size===e.byteLength?e:null}catch{return null}}p(po,"probeCachedTessellation");function Cs(i,t,e=t){if(!Number.isSafeInteger(t)||t<=0||!Number.isSafeInteger(e)||e<t)return null;let n;try{n=Tt.openSync(i,"r");let s=Tt.fstatSync(n);if(!s.isFile()||s.size!==t||s.size>e)return null;let r=Buffer.allocUnsafe(t),o=0;for(;o<r.byteLength;){let c=Tt.readSync(n,r,o,r.byteLength-o,o);if(c<=0)return null;o+=c}let a=Tt.fstatSync(n);return!a.isFile()||a.size!==t?null:new Uint8Array(r.buffer,r.byteOffset,r.byteLength)}catch{return null}finally{if(n!==void 0)try{Tt.closeSync(n)}catch{}}}p(Cs,"readExactObjectBytes");function Is(i,{expectedObject:t,maxBytes:e,env:n=process.env}={}){let s=po(i,n);if(!s||t!==void 0&&s.object!==t)return null;let r=e===void 0?s.byteLength:Number(e);if(!Number.isSafeInteger(r)||r<s.byteLength)return null;let o=Cs(Rs(s.object,n),s.byteLength,r);return!o||di(o)!==s.object||!ws(o,s)?null:o}p(Is,"readCachedTessellationBytes");function _h(i,t){let e=ws(t,{tessellationInput:i});if(!e)throw new TypeError("invalid TESS v4 payload");let n=Ts({schemaVersion:hi,object:di(t),...e},{tessellationInput:i});if(!n)throw new TypeError("invalid TESS v4 mesh record");return n}p(_h,"recordForPayload");function yh(i,t,e){let n=Rs(i.object,e),s=Cs(n,i.byteLength);if(s&&di(s)===i.object)return;fo(n,t);let r=Cs(n,i.byteLength);if(!r||di(r)!==i.object)throw new Error(`tessellation object address mismatch for ${i.object}`)}p(yh,"putObject");function mo(i,t,e=process.env){if(!lo(e))return null;let n=t instanceof Uint8Array?t:new Uint8Array(t),s=_h(i,n),r=po(i,e);if(r&&(r.object!==s.object||r.surfaceObject!==s.surfaceObject)&&Is(i,{expectedObject:r.object,env:e}))throw new Es;return yh(s,n,e),fo(ho(i,e),JSON.stringify(s)),s}p(mo,"writeCachedTessellationBytes");function pi(i){return i<=.04045?i/12.92:((i+.055)/1.055)**2.4}p(pi,"srgbToLinear");function vh(i){return i<=.0031308?i*12.92:1.055*i**(1/2.4)-.055}p(vh,"linearToSrgb");function Mh(i){let t=Math.min(1,Math.max(0,Number(i)||0));return Math.round(Math.min(1,Math.max(0,vh(t)))*255)}p(Mh,"linearChannelToSrgbByte");function ee(i){return!Array.isArray(i)||i.length<3?null:`#${i.slice(0,3).map(e=>Mh(e).toString(16).padStart(2,"0")).join("")}`}p(ee,"linearRgbToHex");var $e=globalThis.Buffer,bh=typeof TextEncoder<"u"?new TextEncoder:null;function Sh(i,t=0){let e=Number(i);return Number.isFinite(e)?e:t}p(Sh,"finiteNumber");function wn(i){return Math.min(Math.max(Sh(i),0),1)}p(wn,"clamp01");function mi(i,t="utf-8"){if($e?.from)return $e.from(String(i),t);if(t!=="utf-8"&&t!=="utf8"){let e=String(i),n=new Uint8Array(e.length);for(let s=0;s<e.length;s+=1)n[s]=e.charCodeAt(s)&255;return n}return bh.encode(String(i))}p(mi,"bytesFromString");function ne(i,t=0){if($e?.alloc)return $e.alloc(i,t);let e=new Uint8Array(i);return t&&e.fill(t),e}p(ne,"allocBytes");function Ye(i,t=void 0){if($e?.concat)return $e.concat(i,t);let e=t??i.reduce((r,o)=>r+o.length,0),n=new Uint8Array(e),s=0;for(let r of i)n.set(r,s),s+=r.length;return n}p(Ye,"concatBytes");function Ut(i){return new Uint8Array(i.buffer,i.byteOffset,i.byteLength)}p(Ut,"typedArrayBytes");function Ps(i){return new DataView(i.buffer,i.byteOffset,i.byteLength)}p(Ps,"viewFor");function st(i,t,e){Ps(i).setUint16(t,e,!0)}p(st,"writeUInt16LE");function ct(i,t,e){Ps(i).setUint32(t,e,!0)}p(ct,"writeUInt32LE");function Ls(i,t,e){Ps(i).setFloat32(t,e,!0)}p(Ls,"writeFloatLE");function xo(i,t,e,n){let s=String(e).slice(0,n);for(let r=0;r<s.length;r+=1)i[t+r]=s.charCodeAt(r)&127}p(xo,"writeAscii");function go(i,t=32){let e=(4-i.length%4)%4;return e?Ye([i,ne(e,t)]):i}p(go,"align4Buffer");function we(i,t="model"){return String(i||t).trim().replace(/[\x00-\x1f<>:"/\\|?*]+/g,"-")||t}p(we,"sanitizeName");function Ns(i){let t=[1/0,1/0,1/0],e=[-1/0,-1/0,-1/0];for(let n=0;n<i.length;n+=3)t[0]=Math.min(t[0],i[n]),t[1]=Math.min(t[1],i[n+1]),t[2]=Math.min(t[2],i[n+2]),e[0]=Math.max(e[0],i[n]),e[1]=Math.max(e[1],i[n+1]),e[2]=Math.max(e[2],i[n+2]);return{min:t.map(n=>Number.isFinite(n)?n:0),max:e.map(n=>Number.isFinite(n)?n:0)}}p(Ns,"boundsForPositions");function _o(i,t="#d4d4d8"){let e=String(i||t).trim(),n=/^#(?:[0-9a-fA-F]{3}){1,2}$/.test(e)?e:t,s=n.length===4?`${n[1]}${n[1]}${n[2]}${n[2]}${n[3]}${n[3]}`:n.slice(1);return[parseInt(s.slice(0,2),16)/255,parseInt(s.slice(2,4),16)/255,parseInt(s.slice(4,6),16)/255]}p(_o,"hexToRgb01");function yo(i,t){let e=go(Ye(t),0);i.buffers=[{byteLength:e.length}];let n=go(mi(JSON.stringify(i)),32),s=20+n.length+8+e.length,r=ne(12);ct(r,0,1179937895),ct(r,4,2),ct(r,8,s);let o=ne(8);ct(o,0,n.length),ct(o,4,1313821514);let a=ne(8);return ct(a,0,e.length),ct(a,4,5130562),Ye([r,o,n,a,e],s)}p(yo,"buildGlb");function Ah(i,t){let e=i[t],n=i[t+1],s=i[t+2],r=i[t+3],o=i[t+4],a=i[t+5],c=i[t+6],l=i[t+7],u=i[t+8],h=r-e,f=o-n,d=a-s,m=c-e,g=l-n,_=u-s,x=f*_-d*g,y=d*m-h*_,v=h*g-f*m,b=Math.hypot(x,y,v);return b>1e-12?[x/b,y/b,v/b]:[0,0,1]}p(Ah,"triangleNormal");function vo(i,{name:t="model"}={}){let e=i.positions||new Float32Array,n=Math.floor(e.length/9),s=ne(84+n*50);xo(s,0,`cad ${we(t)}`,80),ct(s,80,n);let r=84;for(let o=0;o<n;o+=1){let a=o*9,c=Ah(e,a);for(let l of c)Ls(s,r,l),r+=4;for(let l=0;l<9;l+=1)Ls(s,r,e[a+l]),r+=4;st(s,r,0),r+=2}return s}p(vo,"meshToBinaryStl");function Us(i){return String(i??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}p(Us,"xmlEscape");function Ds(i){let t=Ds.table;if(!t){t=new Uint32Array(256);for(let n=0;n<256;n+=1){let s=n;for(let r=0;r<8;r+=1)s=s&1?3988292384^s>>>1:s>>>1;t[n]=s>>>0}Ds.table=t}let e=4294967295;for(let n of i)e=t[(e^n)&255]^e>>>8;return(e^4294967295)>>>0}p(Ds,"crc32");function Mo(i){let t=[],e=[],n=0,s=0,r=33;for(let l of i){let u=mi(l.name),h=l.body instanceof Uint8Array?l.body:mi(String(l.body||"")),f=Ds(h),d=ne(30);ct(d,0,67324752),st(d,4,20),st(d,6,0),st(d,8,0),st(d,10,s),st(d,12,r),ct(d,14,f),ct(d,18,h.length),ct(d,22,h.length),st(d,26,u.length),st(d,28,0),t.push(d,u,h);let m=ne(46);ct(m,0,33639248),st(m,4,20),st(m,6,20),st(m,8,0),st(m,10,0),st(m,12,s),st(m,14,r),ct(m,16,f),ct(m,20,h.length),ct(m,24,h.length),st(m,28,u.length),st(m,30,0),st(m,32,0),st(m,34,0),st(m,36,0),ct(m,38,0),ct(m,42,n),e.push(m,u),n+=d.length+u.length+h.length}let o=n,a=Ye(e),c=ne(22);return ct(c,0,101010256),st(c,4,0),st(c,6,0),st(c,8,i.length),st(c,10,i.length),ct(c,12,a.length),ct(c,16,o),st(c,20,0),Ye([...t,a,c])}p(Mo,"zipStore");var Te=5126,wh=5122,Th=5120,bo=5123,Eh=5125,me=34962,So=34963,Ch=4,Rh=65535,Ee=32767,Fs=127;function Os(i){return i+3&-4}p(Os,"align4");function wo(i,t){if(i.length>=t)return i;let e=new Uint8Array(t);return e.set(i,0),e}p(wo,"padTo");function Ao(i,t,e,n){if(e===t)return wo(i,Os(i.length));let s=new Uint8Array(n*e);for(let r=0;r<n;r+=1)s.set(i.subarray(r*t,(r+1)*t),r*e);return s}p(Ao,"strideElements");function Ih(i,t){let e=i[t],n=i[t+1],s=i[t+2],r=i[t+3],o=i[t+4],a=i[t+5],c=i[t+6],l=i[t+7],u=i[t+8],h=r-e,f=o-n,d=a-s,m=c-e,g=l-n,_=u-s,x=f*_-d*g,y=d*m-h*_,v=h*g-f*m,b=Math.hypot(x,y,v);return b>1e-12?[x/b,y/b,v/b]:[0,0,1]}p(Ih,"faceNormal");function Ph(i,t,{weldDecimals:e=5}={}){let n=Math.floor(i.length/3),s=10**e,r=p(h=>Math.round(h*s)/s,"q"),o=[],a=[],c=new Uint32Array(n),l=new Map,u=t&&t.length===i.length;for(let h=0;h*9<i.length;h+=1){let f=h*9,d=u?null:Ih(i,f);for(let m=0;m<3;m+=1){let g=f+m*3,_=i[g],x=i[g+1],y=i[g+2],v=u?t[g]:d[0],b=u?t[g+1]:d[1],S=u?t[g+2]:d[2],A=`${r(_)},${r(x)},${r(y)},${r(v)},${r(b)},${r(S)}`,M=l.get(A);M===void 0&&(M=o.length/3,l.set(A,M),o.push(_,x,y),a.push(v,b,S)),c[h*3+m]=M}}return{positions:new Float32Array(o),normals:new Float32Array(a),indices:c.subarray(0,Math.floor(i.length/3)*3)}}p(Ph,"weldMesh");function Lh(i,t){let e=i.length/3,n=new Int16Array(i.length),s=[Math.max(t.max[0]-t.min[0],1e-9),Math.max(t.max[1]-t.min[1],1e-9),Math.max(t.max[2]-t.min[2],1e-9)];for(let r=0;r<e;r+=1)for(let o=0;o<3;o+=1){let a=r*3+o,c=(i[a]-t.min[o])/s[o];n[a]=Math.max(-Ee,Math.min(Ee,Math.round(c*Ee)))}return{array:n,scale:s.map(r=>r/Ee),translation:[t.min[0],t.min[1],t.min[2]]}}p(Lh,"quantizePositions");function Nh(i){let t=new Int8Array(i.length);for(let e=0;e<i.length;e+=1)t[e]=Math.max(-Fs,Math.min(Fs,Math.round(i[e]*Fs)));return t}p(Nh,"quantizeNormals");var Dh=.42,Uh=.03;function Tn(i,t){let e=Number(i?.[t]);return Number.isFinite(e)?wn(e):null}p(Tn,"finishChannel");function Fh(i,t,e=null,n=null){let s=_o(i).map(wn).map(pi).map(Math.fround),r=Tn(n,"opacity"),o=e==null?r===null?1:r:wn(e),a=Tn(n,"roughness"),c=Tn(n,"metalness"),l=Tn(n,"clearcoat"),u=Tn(n,"clearcoatRoughness"),h={name:we(t||"material","material"),doubleSided:!0,extras:{cadSourceColor:!0},pbrMetallicRoughness:{baseColorFactor:[...s,o],roughnessFactor:a===null?Dh:a,metallicFactor:c===null?Uh:c}};return o<1&&(h.alphaMode="BLEND"),l!==null&&l>0&&(h.extensions={KHR_materials_clearcoat:{clearcoatFactor:l,...u===null?{}:{clearcoatRoughnessFactor:u}}}),h}p(Fh,"materialFor");var Oh=[["translation",3,"VEC3"],["rotation",4,"VEC4"],["scale",3,"VEC3"]];function Bh(i,{nodeIndexByKey:t,targetCountByKey:e,accessors:n,pushView:s}){let r=[];for(let o of Array.isArray(i)?i:[]){let a=[],c=[],l=new Map,u=p(h=>{let f=l.get(h);if(f!==void 0)return f;if(!h||!h.length)throw new Error("writeGlb: an animation channel needs a non-empty times array");return n.push({bufferView:s(Ut(h)),byteOffset:0,componentType:Te,count:h.length,type:"SCALAR",min:[h[0]],max:[h[h.length-1]]}),f=n.length-1,l.set(h,f),f},"timeAccessorFor");for(let h of o?.channels||[]){let f=t.get(String(h?.node));if(f===void 0)throw new Error(`writeGlb: animation channel targets node ${JSON.stringify(h?.node)}, which no primitive declared`);let d=u(h?.times||o?.times);if(h?.weights){let m=h?.times||o?.times,g=Number(h.targetCount),_=e.get(String(h.node))||0;if(!Number.isInteger(g)||g<1||g!==_)throw new Error(`writeGlb: weights channel on node ${JSON.stringify(h.node)} declares ${h.targetCount} morph targets, but its mesh has ${_}`);if(h.weights.length!==m.length*g)throw new Error(`writeGlb: weights channel on node ${JSON.stringify(h.node)} has ${h.weights.length} scalars for ${m.length} times x ${g} targets`);n.push({bufferView:s(Ut(h.weights)),byteOffset:0,componentType:Te,count:h.weights.length,type:"SCALAR"}),a.push({input:d,output:n.length-1,interpolation:"LINEAR"}),c.push({sampler:a.length-1,target:{node:f,path:"weights"}})}for(let[m,g,_]of Oh){let x=h?.[m];x&&(n.push({bufferView:s(Ut(x)),byteOffset:0,componentType:Te,count:x.length/g,type:_}),a.push({input:d,output:n.length-1,interpolation:"LINEAR"}),c.push({sampler:a.length-1,target:{node:f,path:m}}))}}c.length&&r.push({name:we(o?.name||"clip","clip"),samplers:a,channels:c})}return r}p(Bh,"buildAnimations");function To(i,t={}){let{preset:e="export",name:n="model",units:s="mm",weldDecimals:r=5,encoder:o=null,occurrenceIdPrefix:a=null,upAxis:c="y",animations:l=null,nodeTransforms:u=null}=t,h=String(c).trim().toLowerCase();if(h!=="y"&&h!=="z")throw new Error(`writeGlb: upAxis must be "y" (glTF) or "z" (CAD), got ${JSON.stringify(c)}`);let f=String(a||t.sourceKind||we(n,"model")),d=e==="render";if(d&&!o)throw new Error("writeGlb: preset 'render' requires meshoptimizer's MeshoptEncoder (await MeshoptEncoder.ready)");if(d&&(l||u))throw new Error("writeGlb: preset 'render' spends every node transform on dequantization, so it carries no animation or node TRS \u2014 use preset 'export' for an animated file");let m=Array.isArray(i?.primitives)&&i.primitives.length?i.primitives:[{positions:i?.positions,normals:i?.normals,color:t.color}],g=[],_=[],x=[],y=[],v=[],b=[],S=new Map,A=0,M=p(T=>{let U=Os(A);U>A&&(g.push(new Uint8Array(U-A)),A=U),g.push(T);let F=A;return A+=T.length,F},"appendBytes"),w=p((T,U)=>{let N={buffer:0,byteOffset:M(T),byteLength:T.length};return U&&(N.target=U),_.push(N),_.length-1},"pushView"),I=p((T,{count:U,stride:F,mode:N,target:O})=>{let k=M(T),z={byteLength:U*F,byteStride:F,extensions:{EXT_meshopt_compression:{buffer:0,byteOffset:k,byteLength:T.length,count:U,byteStride:F,mode:N}}};return O&&(z.target=O),_.push(z),_.length-1},"pushCompressedView");for(let T of m){let U=T?.positions instanceof Float32Array?T.positions:new Float32Array(T?.positions||[]);if(!U.length)continue;let F=Array.isArray(T?.targets)&&T.targets.length?T.targets:null;if(F){if(!T?.indices)throw new Error("writeGlb: morph targets need already-indexed input \u2014 a weld can merge two vertices a target moves apart, and the deltas would then be 1:1 with nothing");if(d)throw new Error("writeGlb: preset 'render' quantizes every attribute and carries no morph targets \u2014 use preset 'export' for a deforming file")}let N=T?.indices?{positions:U,normals:T.normals instanceof Float32Array&&T.normals.length===U.length?T.normals:new Float32Array(U.length),indices:T.indices}:Ph(U,T?.normals,{weldDecimals:r}),O=N.positions.length/3,k=Ns(N.positions),z=null;if(typeof T?.colorAt=="function"){z=new Uint16Array(O*4);for(let _t=0;_t<O;_t+=1){let Le=T.colorAt(N.positions[_t*3],N.positions[_t*3+1],N.positions[_t*3+2],N.normals[_t*3],N.normals[_t*3+1],N.normals[_t*3+2]);for(let Ot=0;Ot<3;Ot+=1)z[_t*4+Ot]=Math.round(pi(wn(Number(Le?.[Ot])||0))*65535);z[_t*4+3]=65535}}let H,X,B=null,W,q,$=null,J=null;if(d){let _t=Lh(N.positions,k),Le=Ao(Ut(_t.array),6,8,O),Ot=Ao(Ut(Nh(N.normals)),3,4,O);H=I(o.encodeVertexBuffer(Le,O,8),{count:O,stride:8,mode:"ATTRIBUTES",target:me}),X=I(o.encodeVertexBuffer(Ot,O,4),{count:O,stride:4,mode:"ATTRIBUTES",target:me}),z&&(B=I(o.encodeVertexBuffer(Ut(z),O,8),{count:O,stride:8,mode:"ATTRIBUTES",target:me})),$=_t.scale,J=_t.translation,W={bufferView:H,byteOffset:0,componentType:wh,count:O,type:"VEC3",min:[0,0,0],max:[Ee,Ee,Ee]},q={bufferView:X,byteOffset:0,componentType:Th,count:O,type:"VEC3",normalized:!0}}else H=w(Ut(N.positions),me),X=w(Ut(N.normals),me),z&&(B=w(Ut(z),me)),W={bufferView:H,byteOffset:0,componentType:Te,count:O,type:"VEC3",min:k.min,max:k.max},q={bufferView:X,byteOffset:0,componentType:Te,count:O,type:"VEC3"};let K=O<=Rh,Q=K?new Uint16Array(N.indices):new Uint32Array(N.indices),nt=K?2:4,yt=d?I(o.encodeIndexBuffer(new Uint8Array(Q.buffer,Q.byteOffset,Q.byteLength),Q.length,nt),{count:Q.length,stride:nt,mode:"TRIANGLES",target:So}):w(wo(Ut(Q),Os(Q.byteLength)),So);x.push(W);let Jt=x.length-1;x.push(q);let Rt=x.length-1,ft=null;z&&(x.push({bufferView:B,byteOffset:0,componentType:bo,count:O,type:"VEC4",normalized:!0}),ft=x.length-1),x.push({bufferView:yt,byteOffset:0,componentType:K?bo:Eh,count:Q.length,type:"SCALAR"});let ie=x.length-1,At=F?.map((_t,Le)=>{let Ot=_t?.positionDeltas;if(!(Ot instanceof Float32Array)||Ot.length!==N.positions.length)throw new Error(`writeGlb: morph target ${Le} has ${Ot?.length??"no"} position deltas for ${N.positions.length/3} vertices`);let nr=Ns(Ot);x.push({bufferView:w(Ut(Ot),me),byteOffset:0,componentType:Te,count:O,type:"VEC3",min:nr.min,max:nr.max});let ir={POSITION:x.length-1},rn=_t?.normalDeltas;if(rn){if(!(rn instanceof Float32Array)||rn.length!==N.positions.length)throw new Error(`writeGlb: morph target ${Le} has ${rn.length} normal deltas for ${N.positions.length/3} vertices`);x.push({bufferView:w(Ut(rn),me),byteOffset:0,componentType:Te,count:O,type:"VEC3"}),ir.NORMAL=x.length-1}return ir})||null;b.push(Fh(z?"#ffffff":T?.color,T?.materialName||T?.name,T?.opacity??null,T?.material??null));let xe={attributes:{POSITION:Jt,NORMAL:Rt,...ft===null?{}:{COLOR_0:ft}},indices:ie,material:b.length-1,mode:Ch,...At?{targets:At}:{}},Wt=T?.node===void 0||T?.node===null?`\0primitive:${S.size}`:String(T.node),It=S.get(Wt);if(!It)It={key:Wt,input:T,primitives:[],quantization:null,targetCount:At?At.length:0},S.set(Wt,It);else{if(It.targetCount!==(At?At.length:0))throw new Error(`writeGlb: node ${JSON.stringify(Wt)} mixes primitives with ${It.targetCount} and ${At?At.length:0} morph targets, and glTF weights are per MESH`);if(d)throw new Error(`writeGlb: preset 'render' cannot put two primitives on node ${JSON.stringify(Wt)}: each quantized primitive owns its node's transform`)}It.primitives.push(xe),$&&(It.quantization={scale:$,translation:J})}let E=new Map,L=new Map;for(let T of S.values()){L.set(T.key,T.targetCount),y.push({primitives:T.primitives,...T.targetCount?{weights:new Array(T.targetCount).fill(0)}:{}});let U={mesh:y.length-1,name:we(T.input?.name||n,n),extras:{cadOccurrenceId:String(T.input?.occurrenceId||`${f}:${v.length}`),cadSourceKind:t.sourceKind||"mesh",cadUnits:s,cadUpAxis:h}};T.quantization&&(U.scale=T.quantization.scale,U.translation=T.quantization.translation);let F=u instanceof Map?u.get(T.key):null;F&&(F.translation&&(U.translation=[...F.translation]),F.rotation&&(U.rotation=[...F.rotation]),F.scale&&(U.scale=[...F.scale])),E.set(T.key,v.length),v.push(U)}let D=Bh(l,{nodeIndexByKey:E,targetCountByKey:L,accessors:x,pushView:w}),R=d?["KHR_mesh_quantization","EXT_meshopt_compression"]:[],C=[...R];b.some(T=>T.extensions?.KHR_materials_clearcoat)&&C.push("KHR_materials_clearcoat");let P={asset:{version:"2.0",generator:"cadgen-js writeGlb"},scene:0,scenes:[{nodes:v.map((T,U)=>U)}],nodes:v,meshes:y,materials:b,bufferViews:_,accessors:x,...D.length?{animations:D}:{}};return C.length&&(P.extensionsUsed=C),R.length&&(P.extensionsRequired=R),yo(P,g)}p(To,"writeGlb");var Bs=["stl","glb","3mf"],zh=4194304,Co="#d4d4d8",Ro=["roughness","metalness","clearcoat","clearcoatRoughness","opacity"];function zs(i){if(!i||typeof i!="object"||Array.isArray(i))return null;let t={};for(let e of Ro){let n=Number(i[e]);Number.isFinite(n)&&(t[e]=Math.min(1,Math.max(0,n)))}return Object.keys(t).length?t:null}p(zs,"occurrenceMaterial");function kh(i,t){let e=zs(i),n=Array.isArray(t)&&t.length>=4&&Number.isFinite(Number(t[3]))?Math.min(1,Math.max(0,Number(t[3]))):1;if(n>=.999)return e;let s=e&&Number.isFinite(Number(e.opacity))?e.opacity:1;return{...e||{},opacity:n*s}}p(kh,"occurrenceMaterialWithSourceAlpha");function Eo(i){return i?`|${Ro.map(t=>t in i?i[t]:"").join(",")}`:""}p(Eo,"materialKey");function Io(i,t,e,n=Co){let s=String(t?.component||""),r=/^#[0-9a-fA-F]{6}$/.test(String(t?.baseColor||""))?String(t.baseColor).toUpperCase():ee(t?.color),o=ee(i?.components?.[s]?.color)||null,a=ee(e?.partColor)||null,c=r||o||a||n;return(e?.faceRanges||[]).map(l=>ee(l.color)||c)}p(Io,"occurrenceFaceRangeColors");function ks(i,t,e,n,s,r){s[r]=i[0]*t+i[1]*e+i[2]*n+i[3],s[r+1]=i[4]*t+i[5]*e+i[6]*n+i[7],s[r+2]=i[8]*t+i[9]*e+i[10]*n+i[11]}p(ks,"transformPoint");function Vs(i){return i[0]*(i[5]*i[10]-i[6]*i[9])-i[1]*(i[4]*i[10]-i[6]*i[8])+i[2]*(i[4]*i[9]-i[5]*i[8])}p(Vs,"determinant3");function Gs(i){let t=i[0],e=i[1],n=i[2],s=i[4],r=i[5],o=i[6],a=i[8],c=i[9],l=i[10],u=r*l-o*c,h=o*a-s*l,f=s*c-r*a,d=t*u+e*h+n*f;if(!Number.isFinite(d)||Math.abs(d)<1e-30)return null;let m=1/d;return[u*m,h*m,f*m,(n*c-e*l)*m,(t*l-n*a)*m,(e*a-t*c)*m,(e*o-n*r)*m,(n*s-t*o)*m,(t*r-e*s)*m]}p(Gs,"normalMatrix3");function Hs(i){return!Array.isArray(i)||i.length<12?!0:[1,0,0,0,0,1,0,0,0,0,1,0].every((e,n)=>i[n]===e)}p(Hs,"identityTransform");function Ws(i,t,e={}){let n=e.defaultColor||Co,s=new Map(Object.entries(i.components||{}).map(([g,_])=>[g,ee(_?.color)])),r=Math.max(1,Math.floor(Number(e.maxPrimitiveTriangles)||zh)),o=e.perOccurrence===!0,a=e.hiddenOccurrenceIds instanceof Set?e.hiddenOccurrenceIds:null,c=e.occurrenceOpacity instanceof Map?e.occurrenceOpacity:null,l=e.occurrenceOverrides instanceof Map?e.occurrenceOverrides:null;if(l&&!o)throw new Error("buildPackageMeshPrimitives: occurrenceOverrides needs perOccurrence \u2014 an override is keyed by occurrence, and the flat soup has no occurrence to key it to");let u=[],h=new Map,f=-1;for(let g of i.occurrences||[]){f+=1;let _=String(g.component||""),x=t.get(_);if(!x)continue;let y=String(g.id||_);if(a?.has(y))continue;let v=/^#[0-9a-fA-F]{6}$/.test(String(g?.baseColor||""))?String(g.baseColor).toUpperCase():ee(g.color),b=s.get(_)||null,S=ee(x.partColor)||null,A=v||b||S||n,M=c?.has(y)?c.get(y):null,w=kh(g.material,g.color),I=String(g.materialId||"").trim(),E=String(g.materialName||I).trim(),L=Eo(w)+(I?`|material:${I}`:""),D=l?.get(y);if(D){D.forEach((U,F)=>{let N=`${String(f).padStart(8,"0")}|${U.color}${Eo(U.material||null)}|${String(F).padStart(4,"0")}`;h.set(N,{override:{...U,node:y,name:String(g.name||y),occurrenceId:y,...I?{materialId:I}:{},...E?{materialName:E}:{},...M==null?{}:{opacity:M}}})});continue}let R=Array.isArray(g.transform)?g.transform:null,C=R===null||Hs(R),P=!C&&Vs(R)<0,T=C?null:Gs(R);for(let U of x.faceRanges||[]){let F=Number(U.indexCount)||0,N=Math.max(0,Math.ceil(F/3));if(!N)continue;let O=ee(U.color)||A,k=(o?`${String(f).padStart(8,"0")}|${O}`:O)+L,z=h.get(k);z||h.set(k,z={color:O,material:w,materialId:I,materialName:E,chunks:[],node:o?y:null,name:o?String(g.name||y):null,occurrenceId:o?y:null,opacity:M});let H=z.chunks[z.chunks.length-1];(!H||H.triangles+N>r)&&(H={triangles:0,floatCount:0,positions:null,normals:null,offset:0},z.chunks.push(H)),H.triangles+=N,H.floatCount+=N*9,u.push({tessellation:x,range:U,color:O,chunk:H,transform:C?null:R,mirrored:P,nm:T})}}for(let g of h.values())for(let _ of g.chunks||[])_.positions=new Float32Array(_.floatCount),_.normals=new Float32Array(_.floatCount);for(let g of u){let{positions:_,normals:x,indices:y}=g.tessellation,{range:v,transform:b,mirrored:S,nm:A}=g,M=g.chunk,w=M.positions,I=M.normals,E=M.offset,L=S?[0,2,1]:[0,1,2];for(let D=v.indexStart;D<v.indexStart+v.indexCount;D+=3)for(let R of L){let C=y[D+R],P=_[C*3],T=_[C*3+1],U=_[C*3+2];b===null?(w[E]=P,w[E+1]=T,w[E+2]=U):ks(b,P,T,U,w,E);let F=x[C*3],N=x[C*3+1],O=x[C*3+2],k=F,z=N,H=O;A&&(k=A[0]*F+A[1]*N+A[2]*O,z=A[3]*F+A[4]*N+A[5]*O,H=A[6]*F+A[7]*N+A[8]*O);let X=Math.hypot(k,z,H)||1;I[E]=k/X,I[E+1]=z/X,I[E+2]=H/X,E+=3}M.offset=E}let d=[...h.entries()].sort(([g],[_])=>g<_?-1:1).flatMap(([,g])=>g.override?[g.override]:g.chunks.map(_=>({color:g.color,positions:_.positions,normals:_.normals,...g.node===null?{}:{node:g.node,name:g.name,occurrenceId:g.occurrenceId},...g.opacity===null||g.opacity===void 0?{}:{opacity:g.opacity},...g.material===null?{}:{material:g.material},...g.materialId?{materialId:g.materialId}:{},...g.materialName?{materialName:g.materialName}:{}}))).filter(g=>g.indices?g.indices.length>=3:g.positions.length>=9),m=d.reduce((g,_)=>g+(_.indices?_.indices.length/3:_.positions.length/9),0);return{primitives:d,triangleCount:m}}p(Ws,"buildPackageMeshPrimitives");function Vh({primitives:i},{name:t="model"}={}){let e=0;for(let r of i)e+=r.positions.length;let n=new Float32Array(e),s=0;for(let r of i)n.set(r.positions,s),s+=r.positions.length;return vo({positions:n},{name:t})}p(Vh,"packageMeshToStl");var En=.001;function gi(i,t){let e=new Float32Array(i.length);for(let n=0;n<i.length;n+=3)e[n]=i[n]*t,e[n+1]=i[n+2]*t,e[n+2]=-i[n+1]*t;return e}p(gi,"rotateToYUp");function Gh(i){return i.map(t=>({positionDeltas:gi(t.positionDeltas,En),...t.normalDeltas?{normalDeltas:gi(t.normalDeltas,1)}:{}}))}p(Gh,"yUpTargets");function Hh(i){let t=i.verify;if(!t)return;let{vertexIds:e,posed:n}=t;for(let s=0;s<n.length;s+=1){let r=i.targets[s].positionDeltas;for(let o=0;o<e.length;o+=1){let a=e[o]*3,c=[n[s][o*3]*En,n[s][o*3+2]*En,-n[s][o*3+1]*En];for(let l=0;l<3;l+=1){let u=i.positions[a+l]+r[a+l];if(Math.abs(u-c[l])>Wh)throw new Error(`packageMeshExport: morph target ${s} of ${i.occurrenceId||i.node} rebuilds vertex ${e[o]} as ${u} where the posed tube is ${c[l]} (axis ${l}) \u2014 base and deltas are not in the same space`)}}}}p(Hh,"verifyMorphReconstruction");var Wh=1e-6;function Xh(i){return i.map(t=>{let e={...t,positions:gi(t.positions,En),normals:gi(t.normals,1),...t.targets?{targets:Gh(t.targets)}:{}};return e.targets&&(Hh(e),delete e.verify),e})}p(Xh,"yUpPrimitives");function qh({primitives:i},{name:t="model",animation:e=null}={}){return To({primitives:Xh(i)},{preset:"export",name:t,sourceKind:"step",units:"m",upAxis:"y",...e?{animations:[e],nodeTransforms:e.rest||null}:{}})}p(qh,"packageMeshToGlb");function $h({primitives:i},{name:t="model"}={}){let e=i.map((c,l)=>`      <base name="material-${l}" displaycolor="${Us(c.color.toUpperCase())}FF"/>`).join(`
`),n=[],s=[];i.forEach((c,l)=>{let u=[],h=[],f=new Map,d=c.positions,m=p((_,x,y)=>{let v=`${_}:${x}:${y}`,b=f.get(v);return b===void 0&&(b=f.size,f.set(v,b),u.push(`        <vertex x="${_}" y="${x}" z="${y}"/>`)),b},"vertexId");for(let _=0;_<d.length;_+=9){let x=m(d[_],d[_+1],d[_+2]),y=m(d[_+3],d[_+4],d[_+5]),v=m(d[_+6],d[_+7],d[_+8]);x!==y&&y!==v&&v!==x&&h.push(`        <triangle v1="${x}" v2="${y}" v3="${v}"/>`)}let g=l+2;n.push(`    <object id="${g}" type="model" pid="1" pindex="${l}">
      <mesh>
        <vertices>
${u.join(`
`)}
        </vertices>
        <triangles>
${h.join(`
`)}
        </triangles>
      </mesh>
    </object>`),s.push(`    <item objectid="${g}"/>`)});let r=`<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">
  <metadata name="Title">${Us(t)}</metadata>
  <resources>
    <basematerials id="1">
${e}
    </basematerials>
${n.join(`
`)}
  </resources>
  <build>
${s.join(`
`)}
  </build>
</model>
`;return Mo([{name:"[Content_Types].xml",body:`<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
`},{name:"_rels/.rels",body:`<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
`},{name:"3D/3dmodel.model",body:r}])}p($h,"packageMeshTo3mf");function Po(i,t,e={}){let n=String(t||"").toLowerCase();if(e.animation&&n!=="glb")throw new Error(`${n||"(no format)"} carries no animation: only glb does \u2014 export the clip as .glb, or drop the animation for a static mesh`);if(n==="stl")return{body:Vh(i,e),contentType:"model/stl",extension:".stl"};if(n==="glb")return{body:qh(i,e),contentType:"model/gltf-binary",extension:".glb"};if(n==="3mf")return{body:$h(i,e),contentType:"model/3mf",extension:".3mf"};throw new Error(`Unsupported package mesh export format: ${t}`)}p(Po,"packageMeshToFormat");var Ce=1e-7,Xs=.05,qs={vertices:0,worstReach:0};var Lo=7e5,Yh=128,je=p((i,t)=>i.map((e,n)=>e+t[n]),"add"),Ft=p((i,t)=>i.map((e,n)=>e-t[n]),"sub"),St=p((i,t)=>i.map(e=>e*t),"mul"),ht=p((i,t)=>i.reduce((e,n,s)=>e+n*t[s],0),"dot"),ge=p((i,t)=>[i[1]*t[2]-i[2]*t[1],i[2]*t[0]-i[0]*t[2],i[0]*t[1]-i[1]*t[0]],"cross"),Ht=p(i=>Math.hypot(...i),"length"),No=p((i,t)=>(i[0]-t[0])**2+(i[1]-t[1])**2+(i[2]-t[2])**2,"distanceSq");function Zh(i,t){let e=0;for(let n=0;n<3;n++)e+=Math.max(i.min[n]-t[n],0,t[n]-i.max[n])**2;return e}p(Zh,"boundsDistanceSq");function rt(i){throw new Error(`animation deformTube: ${i}`)}p(rt,"fail");function Et(i,t){return(!Array.isArray(i)||i.length!==3||!i.every(Number.isFinite))&&rt(`${t} must be a finite vec3`),i.slice()}p(Et,"vector");function Je(i,t){let e=Ht(i);return e<Ce&&rt(`${t} must be nonzero`),St(i,1/e)}p(Je,"unit");function Qe(i,t,e){(!i||typeof i!="object"||Array.isArray(i))&&rt(`${e} must be an object`);for(let n of Object.keys(i))t.includes(n)||rt(`unknown ${e} key ${JSON.stringify(n)}; expected ${t.join(", ")}`)}p(Qe,"keys");function xi(i,t,e){let n=Math.cos(e),s=Math.sin(e);return je(je(St(i,n),St(ge(t,i),s)),St(t,ht(t,i)*(1-n)))}p(xi,"rotate");function Rn(i,t){let e=1-t;return[0,1,2].map(n=>e*e*e*i[0][n]+3*e*e*t*i[1][n]+3*e*t*t*i[2][n]+t*t*t*i[3][n])}p(Rn,"bezierAt");function tn(i,t){let e=1-t;return[0,1,2].map(n=>3*e*e*(i[1][n]-i[0][n])+6*e*t*(i[2][n]-i[1][n])+3*t*t*(i[3][n]-i[2][n]))}p(tn,"bezierDerivative");function Bo(i,t){return[0,1,2].map(e=>6*(1-t)*(i[2][e]-2*i[1][e]+i[0][e])+6*t*(i[3][e]-2*i[2][e]+i[1][e]))}p(Bo,"bezierSecond");var Jh=[0,.5384693101056831,-.5384693101056831,.906179845938664,-.906179845938664],Kh=[.5688888888888889,.4786286704993665,.4786286704993665,.2369268850561891,.2369268850561891];function Cn(i,t,e){let n=(t+e)/2,s=(e-t)/2,r=0;for(let o=0;o<5;o++){let a=n+s*Jh[o],c=1-a,l=3*c*c,u=6*c*a,h=3*a*a,f=l*(i[1][0]-i[0][0])+u*(i[2][0]-i[1][0])+h*(i[3][0]-i[2][0]),d=l*(i[1][1]-i[0][1])+u*(i[2][1]-i[1][1])+h*(i[3][1]-i[2][1]),m=l*(i[1][2]-i[0][2])+u*(i[2][2]-i[1][2])+h*(i[3][2]-i[2][2]);r+=Kh[o]*Math.hypot(f,d,m)}return s*r}p(Cn,"bezierLength");function zo(i,t,e){let n=ge(t,e),s=Ht(n),r=ht(t,e);return s<Ce?(r<0&&rt("path tangent reverses"),i.slice()):xi(i,St(n,1/s),Math.atan2(s,r))}p(zo,"transport");function jh(i){let t=[{t:0,s:0,tangent:i.tangent,normal:i.normal}],e=p((n,s,r=0)=>{let o=(n+s)/2,a=Cn(i.points,n,s),c=Cn(i.points,n,o),l=Cn(i.points,o,s),u=Je(tn(i.points,n),"Bezier tangent"),h=Je(tn(i.points,s),"Bezier tangent");if(r<20&&(s-n>1/128||Math.abs(a-c-l)>1e-9||ht(u,h)<.9999)){e(n,o,r+1),e(o,s,r+1);return}ht(u,h)<.99&&rt("Bezier has a cusp or unresolved tangent");let f=t.at(-1);t.push({t:s,s:f.s+c+l,tangent:h,normal:zo(f.normal,f.tangent,h)})},"append");e(0,1),i.table=t,i.length=t.at(-1).s}p(jh,"buildBezierTable");function ko(i,t){let e=i.table,n=0,s=e.length-1;for(;s-n>1;){let c=n+s>>1;e[c].s<t?n=c:s=c}let r=e[n],o=e[s],a=r.t+(o.t-r.t)*(t-r.s)/(o.s-r.s);for(let c=0;c<3;c++){let l=r.s+Cn(i.points,r.t,a)-t;if(Math.abs(l)<1e-11)break;a=Math.max(r.t,Math.min(o.t,a-l/Ht(tn(i.points,a))))}return{t:a,lower:r}}p(ko,"bezierParameter");function Vo(i,t){return i.kind==="line"?je(i.start,St(i.tangent,t)):i.kind==="bezier"?Rn(i.points,ko(i,t).t):je(i.center,xi(i.radial,i.axis,t/i.radius*i.sign))}p(Vo,"segmentPoint");function $s(i,t){if(i.kind==="bezier"){let{t:a,lower:c}=ko(i,t),l=tn(i.points,a),u=Ht(l),h=St(l,1/u),f=zo(c.normal,c.tangent,h),d=Bo(i.points,a),m=St(Ft(d,St(h,ht(d,h))),1/(u*u));return{point:Rn(i.points,a),tangent:h,normal:f,binormal:ge(h,f),curvature:m}}let e=i.kind==="arc"?t/i.radius*i.sign:0,n=e?xi(i.tangent,i.axis,e):i.tangent,s=e?xi(i.normal,i.axis,e):i.normal,r=Vo(i,t),o=i.kind==="arc"?St(Ft(i.center,r),1/(i.radius*i.radius)):[0,0,0];return{point:r,tangent:n,normal:s,binormal:ge(n,s),curvature:o}}p($s,"segmentFrame");var _i={line:["kind","start","end"],arc:["kind","center","axis","start","sweepDeg"],bezier:["kind","points"]};function Qh(i,t){if(Qe(i,_i[i.kind]||_i.arc,`segment ${t}`),i.kind==="line"){let e=Et(i.start,"start"),n=Et(i.end,"end"),s=Ft(n,e);return{kind:"line",start:e,end:n,tangent:Je(s,"line"),length:Ht(s),radius:1/0}}if(i.kind==="arc"){let e=Et(i.center,"center"),n=Et(i.start,"start"),s=Je(Et(i.axis,"axis"),"axis"),r=Ft(n,e),o=Ht(r),a=i.sweepDeg*Math.PI/180;(!Number.isFinite(a)||Math.abs(a)<Ce||Math.abs(a)>2*Math.PI+Ce)&&rt("arc sweepDeg must be nonzero and at most 360 degrees"),(o<Ce||Math.abs(ht(r,s))>Ce*Math.max(1,o))&&rt("arc start must be in its normal plane with nonzero radius");let c=Math.sign(a),l=St(ge(s,r),c/o),u={kind:"arc",center:e,start:n,axis:s,radial:r,radius:o,sign:c,tangent:l,length:o*Math.abs(a)};return u.end=Vo(u,u.length),u}if(i.kind==="bezier"){(!Array.isArray(i.points)||i.points.length!==4)&&rt("Bezier points must contain four vec3 control points");let e=i.points.map(n=>Et(n,"Bezier point"));return{kind:"bezier",points:e,start:e[0],end:e[3],tangent:Je(tn(e,0),"Bezier tangent"),radius:1/0}}return rt(`unknown segment kind ${JSON.stringify(i.kind)}; expected line, arc, bezier`)}p(Qh,"compileSegment");function tf(i){return Math.min(...i.table.map(t=>{let e=tn(i.points,t.t),n=Bo(i.points,t.t),s=Ht(e);return Math.pow(s,3)/Ht(ge(e,n))}))}p(tf,"sampledBezierRadius");function ef(i){if(i.kind==="arc")return{min:i.center.map(e=>e-i.radius),max:i.center.map(e=>e+i.radius)};let t=i.kind==="bezier"?i.points:[i.start,i.end];return{min:[0,1,2].map(e=>Math.min(...t.map(n=>n[e]))),max:[0,1,2].map(e=>Math.max(...t.map(n=>n[e])))}}p(ef,"segmentBounds");function nf(i){Qe(i,["segments","normal"],"path"),(!Array.isArray(i.segments)||!i.segments.length)&&rt("path needs at least one segment"),i.normal===void 0&&rt("path normal is required: give both the rest and the posed path an explicit transverse normal seed");let t=Et(i.normal,"normal"),e=0,n=null,s=i.segments.map((o,a)=>{let c=Qh(o,a);if(n){Ht(Ft(n.end,c.start))>1e-5&&rt(`path discontinuity before segment ${a}`);let l=$s(n,n.length);ht(l.tangent,c.tangent)<1-1e-7&&rt(`path is not tangent-continuous before segment ${a}`),c.normal=l.normal}else c.normal=Je(Ft(t,St(c.tangent,ht(t,c.tangent))),"path normal transverse to first tangent");return c.kind==="bezier"&&jh(c),c.offset=e,c.bounds=ef(c),e+=c.length,n=c,c}),r={segments:s,length:e};return Object.defineProperty(r,"minRadius",{get(){for(let o of s)o.kind==="bezier"&&o.radius===1/0&&(o.radius=tf(o));return Math.min(...s.map(o=>o.radius))}}),r}p(nf,"compileTubePath");function yi(i,t){Number.isFinite(t)||rt("path distance must be finite");let e=t<=0?i.segments[0]:i.segments.find(o=>t<=o.offset+o.length)||i.segments.at(-1),n=t-e.offset,s=Math.max(0,Math.min(e.length,n)),r=$s(e,s);return n!==s&&(r.point=je(r.point,St(r.tangent,n-s))),r}p(yi,"sampleTubePath");function sf(i){if(!i.tablePoints){let t=new Float64Array(i.table.length*3);i.table.forEach((e,n)=>{let s=Rn(i.points,e.t);t[n*3]=s[0],t[n*3+1]=s[1],t[n*3+2]=s[2]}),i.tablePoints=t}return i.tablePoints}p(sf,"tablePoints");function rf(i,t){let e=sf(i),n=0,s=1/0;for(let l=0;l<i.table.length;l++){let u=(t[0]-e[l*3])**2+(t[1]-e[l*3+1])**2+(t[2]-e[l*3+2])**2;u<s&&(s=u,n=l)}let r=i.table[Math.max(0,n-1)].t,o=i.table[Math.min(i.table.length-1,n+1)].t;for(let l=0;l<35;l++){let u=r+(o-r)/3,h=o-(o-r)/3;No(t,Rn(i.points,u))<No(t,Rn(i.points,h))?o=h:r=u}let a=(r+o)/2,c=i.table.findLast(l=>l.t<=a)||i.table[0];return c.s+Cn(i.points,c.t,a)}p(rf,"closestBezierDistance");function of(i,t){let e=Ft(t,i.center),n=Math.atan2(ht(ge(i.radial,e),i.axis),ht(i.radial,e))*i.sign;n<0&&(n+=2*Math.PI);let s=n*i.radius;return s>i.length?Ht(Ft(t,i.start))<Ht(Ft(t,i.end))?0:i.length:s}p(of,"closestArcDistance");function Go(i,t){let e=null,n=i.segments.map(s=>({segment:s,bound:Zh(s.bounds,t)})).sort((s,r)=>s.bound-r.bound);for(let{segment:s,bound:r}of n){if(e&&r>e.distanceSq+1e-12)break;let o;s.kind==="line"?o=ht(Ft(t,s.start),s.tangent):s.kind==="bezier"?o=rf(s,t):o=of(s,t),o=Math.max(0,Math.min(s.length,o));let a=$s(s,o),c=Ft(t,a.point),l=ht(c,c);(!e||l<e.distanceSq)&&(e={distance:s.offset+o,distanceSq:l,transverse:[ht(c,a.normal),ht(c,a.binormal)],axial:ht(c,a.tangent)})}return e}p(Go,"projectTubePath");var Ze=new Map;function Do(i){let t=JSON.stringify(i),e=Ze.get(t);return e?Ze.delete(t):e=nf(i),Ze.set(t,e),Ze.size>Yh&&Ze.delete(Ze.keys().next().value),e}p(Do,"cachedCompile");function Uo(i){Qe(i,["segments","normal"],"path"),(!Array.isArray(i.segments)||!i.segments.length)&&rt("path needs at least one segment"),i.normal===void 0&&rt("path normal is required: give both the rest and the posed path an explicit transverse normal seed");let t=Et(i.normal,"normal"),e=i.segments.map((n,s)=>(Qe(n,_i[n.kind]||_i.arc,`segment ${s}`),n.kind==="line"?{kind:"line",start:Et(n.start,"start"),end:Et(n.end,"end")}:n.kind==="arc"?{kind:"arc",center:Et(n.center,"center"),axis:Et(n.axis,"axis"),start:Et(n.start,"start"),sweepDeg:n.sweepDeg}:n.kind==="bezier"?((!Array.isArray(n.points)||n.points.length!==4)&&rt("Bezier points must contain four vec3 control points"),{kind:"bezier",points:n.points.map(r=>Et(r,"Bezier point"))}):rt(`unknown segment kind ${JSON.stringify(n.kind)}; expected line, arc, bezier`)));return{normal:t,segments:e}}p(Uo,"canonicalPathSpec");function Ke(i,t){if(i===t)return!0;if(Array.isArray(i))return!Array.isArray(t)||i.length!==t.length?!1:i.every((e,n)=>Ke(e,t[n]));if(i&&typeof i=="object"){if(!t||typeof t!="object"||Array.isArray(t))return!1;let e=Object.keys(i);return e.length===Object.keys(t).length&&e.every(n=>Ke(i[n],t[n]))}return!1}p(Ke,"sameNumbers");function vi(i,t){return i===t?!0:!i||!t?!1:i.twistDeg===t.twistDeg&&i.maxSegmentLength===t.maxSegmentLength&&Ke(i.braid,t.braid)&&Ke(i.restSpec,t.restSpec)&&Ke(i.pathSpec,t.pathSpec)}p(vi,"sameTubeDeformation");function Ho(i,t){return i.maxSegmentLength===t.maxSegmentLength&&Ke(i.restSpec,t.restSpec)}p(Ho,"sameTubeRestShape");function Re(i){return{...i,rest:Do(i.restSpec),path:Do(i.pathSpec)}}p(Re,"compileDeformation");function Wo(i){Qe(i,["rest","path","twistDeg","maxSegmentLength","braid"],"deformation");let t=i.twistDeg??0;Number.isFinite(t)||rt("twistDeg must be finite");let e=i.maxSegmentLength??1;(!Number.isFinite(e)||e<.05)&&rt("maxSegmentLength must be at least 0.05 mm");let n=null;if(i.braid){Qe(i.braid,["pitch","depth","strands"],"braid");let{pitch:s,depth:r,strands:o}=i.braid;Number.isFinite(s)&&s>0&&Number.isFinite(r)&&r>=0&&Number.isInteger(o)&&o>=2&&o<=64&&o%2===0||rt("braid needs positive pitch, nonnegative depth, and an even strand count from 2 to 64"),n={pitch:s,depth:r,strands:o}}return{restSpec:Uo(i.rest),pathSpec:Uo(i.path),twistDeg:t,maxSegmentLength:e,braid:n}}p(Wo,"normalizeTubeDeformation");var af=p(i=>JSON.stringify([i.restSpec,i.maxSegmentLength]),"restMappingKey");function Fo(i,t,e){let n=[];for(let s=0;s<i.length;s++){let r=i[s],o=i[(s+1)%i.length],a=e?r[0]>=t:r[0]<=t,c=e?o[0]>=t:o[0]<=t;if(a&&n.push(r),a!==c){let l=(t-r[0])/(o[0]-r[0]);n.push(r.map((u,h)=>u+l*(o[h]-u)))}}return n.filter((s,r)=>!r||Math.abs(s[1]-n[r-1][1])+Math.abs(s[2]-n[r-1][2])+Math.abs(s[3]-n[r-1][3])>1e-10)}p(Fo,"clipPolygon");function cf(i,t,e,n,s){if(s>=e.length)return{geometry:t,sourceTriangles:null};let r=t.attributes.position,o=new i.Vector3,a=new Float64Array(r.count),c=new Map;for(let x=0;x<r.count;x++){let y=[r.getX(x),r.getY(x),r.getZ(x)].join(","),v=c.get(y);v===void 0&&(o.fromBufferAttribute(r,x).applyMatrix4(n),v=Go(e,o.toArray()).distance,c.set(y,v)),a[x]=v}c.clear();let l=t.index?.count??r.count;if(l%3)return{geometry:t.clone(),sourceTriangles:null};let u=Object.entries(t.attributes),h=Object.fromEntries(u.map(([x])=>[x,[]])),f=[],d=[],m=new Map,g=p(x=>t.index?t.index.getX(x):x,"index");for(let x=0;x<l;x+=3){let y=[g(x),g(x+1),g(x+2)],v=y.map(M=>a[M]),b=v.map((M,w)=>[M,...[0,1,2].map(I=>w===I?1:0)]),S=Math.floor(Math.min(...v)/s),A=Math.floor(Math.max(...v)/s);for(let M=S;M<=A;M++){let w=Fo(Fo(b,M*s,!0),(M+1)*s,!1);for(let I=1;I<w.length-1;I++){let E=[w[0],w[I],w[I+1]],L=Ft(E[1].slice(1),E[0].slice(1)),D=Ft(E[2].slice(1),E[0].slice(1));if(!(Ht(ge(L,D))<1e-12)){f.push(x/3),f.length>Lo&&rt(`refined tube exceeds ${Lo} triangles; increase maxSegmentLength`);for(let R of E){let C=y.map((T,U)=>[T,Math.round(R[U+1]*1e10)]).filter(([,T])=>T).sort((T,U)=>T[0]-U[0]).map(T=>T.join(":")).join(","),P=m.get(C);if(P===void 0){P=m.size,m.set(C,P);for(let[T,U]of u)for(let F=0;F<U.itemSize;F++)h[T].push(y.reduce((N,O,k)=>N+R[k+1]*U.getComponent(O,F),0))}d.push(P)}}}}}let _=t.clone();for(let[x,y]of u)_.setAttribute(x,new i.Float32BufferAttribute(h[x],y.itemSize));return _.setIndex(d),_.clearGroups(),{geometry:_,sourceTriangles:new Uint32Array(f)}}p(cf,"refineRestMesh");function lf(i,t,e,n,s,r=!1){let o=[],a=r?new Float32Array(t.count):new Uint32Array(t.count),c=new Map,l=new i.Vector3,u=new i.Matrix3().getNormalMatrix(s),h=new i.Vector3;for(let d=0;d<t.count;d++){let m=[t.getX(d),t.getY(d),t.getZ(d),...e?[e.getX(d),e.getY(d),e.getZ(d)]:[]].join(","),g=c.get(m);if(g!==void 0){a[d]=g;continue}let _=o.length/8;c.set(m,_),a[d]=_,l.fromBufferAttribute(t,d).applyMatrix4(s);let x=Go(n,[l.x,l.y,l.z]),y=yi(n,x.distance),v=je(St(y.normal,x.transverse[0]),St(y.binormal,x.transverse[1])),b=1-ht(y.curvature,v);b<=Ce&&rt("rest mesh crosses the centerline curvature radius");let S=[0,0,0];if(e){h.fromBufferAttribute(e,d).applyNormalMatrix(u);let A=[h.x,h.y,h.z];S=[ht(A,y.normal),ht(A,y.binormal),ht(A,y.tangent)]}o.push(x.distance/n.length,...x.transverse,x.axial,...S,b)}let f=r?new Float32Array(Math.ceil(o.length/4096)*4096):new Float64Array(o.length);return f.set(o),{values:f,indices:a,gpu:r}}p(lf,"mappingFor");function uf(i,t,e,n,s,r){let{path:o,rest:a}=s,c=new i.Vector3,l=new i.Vector3,u=new i.Matrix3().getNormalMatrix(r),h=s.twistDeg*Math.PI/180,f=Math.cos(h),d=Math.sin(h),m=o.length/a.length,g=new Map,_=n.values,x=new Map;for(let y=0;y<t.count;y++){let v=n.indices[y],b=x.get(v);if(b!==void 0){t.setXYZ(y,t.getX(b),t.getY(b),t.getZ(b)),e&&e.setXYZ(y,e.getX(b),e.getY(b),e.getZ(b));continue}x.set(v,y);let S=v*8,A=_[S],M=g.get(A);M||(M=yi(o,A*o.length),g.set(A,M));let w=f*_[S+1]-d*_[S+2],I=d*_[S+1]+f*_[S+2],E=M.normal[0]*w+M.binormal[0]*I,L=M.normal[1]*w+M.binormal[1]*I,D=M.normal[2]*w+M.binormal[2]*I,R=M.curvature[0]*E+M.curvature[1]*L+M.curvature[2]*D;if(1-R<=Xs){let P=(1-Xs)/R;E*=P,L*=P,D*=P,qs.vertices+=1,qs.worstReach=Math.max(qs.worstReach,R),R=1-Xs}let C=1-R;if(c.set(M.point[0]+E+_[S+3]*M.tangent[0],M.point[1]+L+_[S+3]*M.tangent[1],M.point[2]+D+_[S+3]*M.tangent[2]).applyMatrix4(r),t.setXYZ(y,c.x,c.y,c.z),e){let P=f*_[S+4]-d*_[S+5],T=d*_[S+4]+f*_[S+5],U=_[S+6]*_[S+7]/(C*m);l.set(P*M.normal[0]+T*M.binormal[0]+U*M.tangent[0],P*M.normal[1]+T*M.binormal[1]+U*M.tangent[1],P*M.normal[2]+T*M.binormal[2]+U*M.tangent[2]).applyNormalMatrix(u),e.setXYZ(y,l.x,l.y,l.z)}}t.needsUpdate=!0,e&&(e.needsUpdate=!0)}p(uf,"updateAttribute");var Oo=new WeakMap;function hf(i,t){return`${af(i)}|${t.elements.map(e=>Number(e).toPrecision(9)).join(",")}`}p(hf,"restPreparationKey");function ff(i,t,e,n){let s=Oo.get(t);s||(s=new Map,Oo.set(t,s));let r=hf(e,n),o=s.get(r);if(!o){let a=cf(i,t,e.rest,n,e.maxSegmentLength);o={restSource:a.geometry,sourceTriangles:a.sourceTriangles,mappings:new Map},s.set(r,o)}return o}p(ff,"prepareRestSurface");function df(i,t,e,n,s){let r=s?"gpu":"exact",o=t.mappings.get(r);return o||(o=lf(i,t.restSource.attributes.position,t.restSource.attributes.normal,e.rest,n,s),t.mappings.set(r,o)),o}p(df,"preparedMapping");function Xo(i,t,e,n){let s=ff(i,t,e,n);return{geometry:s.restSource,sourceTriangles:s.sourceTriangles,mapping:df(i,s,e,n,!1),vertexCount:s.restSource.attributes.position.count}}p(Xo,"prepareTubeBake");function Mi(i,t,e,n,s,r=null){uf(i,s,r,t.mapping,e,n)}p(Mi,"poseTubeBake");function qo(i){return!!i&&typeof i=="object"&&!Array.isArray(i)}p(qo,"isObject");var pf=Math.PI/180;function $o(i){let t={};for(let[e,n]of Object.entries(qo(i)?i:{})){if(!qo(n)||typeof n.update!="function")continue;let s=Number(n.duration);t[String(e)]={id:String(e),label:String(n.label||e),duration:Number.isFinite(s)&&s>0?s:1,loop:n.loop!==!1,update:n.update}}return t}p($o,"normalizeAnimationClips");function mf(i){let t=new Map;for(let e of i?.parts||[]){let n=String(e.label||e.name||"").trim();n&&(t.has(n)||t.set(n,[]),t.get(n).push(String(e.id)))}return t}p(mf,"partIdsByLabel");function gf(i,t){let e=String(t).replace(/^#/,"").split(",").map(s=>s.trim()).filter(Boolean);if(!e.length||!e.every(s=>/^o[\d.]+$/.test(s)))return null;let n=[];for(let s of i?.parts||[]){let r=String(s.id);e.some(o=>r===o||r.startsWith(`${o}.`))&&n.push(r)}return n.length?n:null}p(gf,"partIdsForOccurrenceRefs");function xf(i,t){let e=mf(t),n=new Map,s=new Map,r=new Map;return{model:{get:p(c=>{let l=e.get(String(c).replace(/^#/,""))||e.get(String(c))||gf(t,c);if(!l||!l.length){let f=[...e.keys()].sort().join(", ")||"(none)";throw new Error(`animation: no occurrence labeled ${JSON.stringify(c)}; labels: ${f}`)}let u=p(f=>{for(let d of l){let m=n.get(d);n.set(d,m?new i.Matrix4().multiplyMatrices(f,m):f.clone())}},"applyMatrix"),h=p((f,d)=>{for(let m of l){let g=s.get(m)||{};g[f]=d,s.set(m,g)}},"setStyle");return{deformTube(f){let d=Wo(f);for(let m of l)r.set(m,d);return this},rotate(f,d,m=[0,0,0]){let g=new i.Vector3(f[0],f[1],f[2]).normalize(),_=new i.Matrix4().makeRotationAxis(g,(Number(d)||0)*pf),x=new i.Matrix4().makeTranslation(-m[0],-m[1],-m[2]),y=new i.Matrix4().makeTranslation(m[0],m[1],m[2]);return u(new i.Matrix4().multiplyMatrices(y,new i.Matrix4().multiplyMatrices(_,x))),this},translate(f){return u(new i.Matrix4().makeTranslation(Number(f[0])||0,Number(f[1])||0,Number(f[2])||0)),this},opacity(f){return h("opacity",Math.max(0,Math.min(1,Number(f)))),this},visible(f){return h("visible",!!f),this}}},"handleFor"),labels:p(()=>[...e.keys()].sort(),"labels")},matrices:n,styles:s,deformations:r}}p(xf,"createAnimationFrame");function Ys(i,t,e,n){let s=xf(i,t),r=e.duration||1,o=Math.max(0,Number(n)||0);return e.loop!==!1?o=o%r:o=Math.min(o,r),e.update(o,s.model),{matrices:s.matrices,styles:s.styles,deformations:s.deformations}}p(Ys,"evaluateAnimationClip");function _f(i){return String(i??"").trim()}p(_f,"normalizeString");function Zs(i){return Math.max(Number(i?.duration)||0,.001)}p(Zs,"animationClipDuration");function Yo(i){return!i||typeof i!="object"?[]:Object.values(i).filter(t=>t&&typeof t.update=="function").map(t=>({id:String(t.id),label:String(t.label||t.id),duration:Zs(t),loop:t.loop!==!1}))}p(Yo,"animationClipList");function Zo(i,t){let e=_f(t);if(!e||!i||typeof i!="object")return null;let n=i[e];return n&&typeof n.update=="function"?n:null}p(Zo,"findAnimationClip");var Jo=1,Ko=120,jo=7200;function en(i){return`${Number(i.toFixed(3))}s`}p(en,"formatSeconds");function Qo(i,t,{label:e="frame"}={}){let n=i&&typeof i=="object"?i:{},s=Number(n.fps??30);if(!Number.isInteger(s)||s<Jo||s>Ko)throw new Error(`${e} fps must be a whole number ${Jo}..${Ko}, got ${JSON.stringify(n.fps)}`);let r=n.start===void 0||n.start===null?0:Number(n.start);if(!Number.isFinite(r)||r<0)throw new Error(`${e} start must be seconds >= 0, got ${JSON.stringify(n.start)}`);let o=Zs(t);if(r>=o)throw new Error(`${e} start ${en(r)} is at or past the end of a ${en(o)} clip: every frame would be the same one`);let a=t?.loop!==!1,c=n.seconds===void 0||n.seconds===null?a?o:o-r:Number(n.seconds);if(!Number.isFinite(c)||c<=0)throw new Error(`${e} seconds must be a positive number, got ${JSON.stringify(n.seconds)}`);let l=Math.max(1,Math.round(c*s));if(l>jo)throw new Error(`${e} ${en(c)} at ${s} fps schedules ${l} frames, past the ${jo}-frame ceiling`);let u=[];return!a&&r+c-o>1e-9&&u.push(`${e} covers ${en(r)}..${en(r+c)} of a ${en(o)} clip that does not loop: every frame past its end is the same final pose`),{fps:s,seconds:c,start:r,frameCount:l,warnings:u}}p(Qo,"resolveFramePlan");function ta(i,t){return i.start+t/i.fps}p(ta,"framePlanElapsedSec");var yf={Matrix4:gt,Vector3:V},Js=Object.freeze(["opacity","visible"]),ea=Object.freeze(["refuse","morph","rest"]),vf=4,Mf=96;function bf(i){let t=Math.max(vf,Math.ceil(Mf/i.fps));return{multiple:t,hz:i.fps*t,count:(i.frameCount-1)*t+1}}p(bf,"morphFitGrid");var bi=.001;function Sf(){return new gt().set(bi,0,0,0,0,0,bi,0,0,-bi,0,0,0,0,0,1)}p(Sf,"cadToGlbBasis");function Af(){let i=1/bi;return new gt().set(i,0,0,0,0,0,-i,0,0,i,0,0,0,0,0,1)}p(Af,"glbToCadBasis");var wf=1e-12,Tf=new gt().elements;function Ef(i){let t=i.elements;for(let e=0;e<16;e+=1)if(Math.abs(t[e]-Tf[e])>wf)return!1;return!0}p(Ef,"isIdentityMatrix");function Cf(i){let t=[];for(let e of i?.occurrences||[]){let n=String(e?.id||"").trim(),s=String(e?.component||"").trim(),r=n||s;if(!r)continue;let o=String(e?.name||n||s).trim();t.push({id:r,occurrenceId:r,componentId:s,name:o,label:o})}return{parts:t}}p(Cf,"animationTargetsFromDescriptor");function Ie(i,t=6){let e=[...i].sort();return e.length<=t?e.join(", "):`${e.slice(0,t).join(", ")} (and ${e.length-t} more)`}p(Ie,"summarize");function Rf(i){let t={translations:[],rotations:[],scales:[],count:0};for(let e=0;e<i;e+=1)js(t,null);return t}p(Rf,"newTrack");var na=new V,ia=new $t,sa=new V;function js(i,t){let e=0,n=0,s=0,r=0,o=0,a=0,c=1,l=1,u=1,h=1;if(t!==null&&(t.decompose(na,ia,sa),{x:e,y:n,z:s}=na,{x:r,y:o,z:a,w:c}=ia,{x:l,y:u,z:h}=sa),i.count>0){let f=(i.count-1)*4;i.rotations[f]*r+i.rotations[f+1]*o+i.rotations[f+2]*a+i.rotations[f+3]*c<0&&(r=-r,o=-o,a=-a,c=-c)}i.translations.push(e,n,s),i.rotations.push(r,o,a,c),i.scales.push(l,u,h),i.count+=1}p(js,"appendSample");function Ks(i,t,e){for(let n=1;n<e;n+=1)for(let s=0;s<t;s+=1)if(Math.fround(i[n*t+s])!==Math.fround(i[s]))return!0;return!1}p(Ks,"varies");function If(i,t){for(let e=0;e<t*3;e+=1)if(Math.fround(i[e])!==1)return!1;return!0}p(If,"scaleIsUnit");function ra(i,t,e,{drop:n=[],deform:s="refuse"}={}){let r=new Set(n.map(E=>String(E).trim())),o=[...r].filter(E=>!Js.includes(E));if(o.length)throw new Error(`animation drop names ${o.sort().join(", ")}, which is not an effect this export can bake static; droppable effects: ${Js.join(", ")}`);let a=String(s||"refuse");if(!ea.includes(a))throw new Error(`animation deform must be one of ${ea.join(", ")}, got ${JSON.stringify(s)}`);let c=Cf(i),l=Sf(),u=Af(),h=new gt,f=new Map,d=new Map,m=new Set,g=new Set,_=new Set,x=new Set,y=new Map,v=new Set,b=a==="morph"?bf(e):{multiple:1,hz:e.fps,count:e.frameCount};for(let E=0;E<b.count;E+=1){let L=ta(e,E/b.multiple),D=Ys(yf,c,t,L),R=E%b.multiple===0?E/b.multiple:-1;if(R>=0){for(let[C,P]of D.matrices){let T=f.get(C);if(!T){if(Ef(P))continue;T=Rf(R),f.set(C,T)}h.multiplyMatrices(l,P).multiply(u),js(T,h)}for(let C of f.values())C.count===R&&js(C,null);for(let[C,P]of D.styles)P&&Object.hasOwn(P,"opacity")&&(g.add(C),R===0&&d.set(C,P.opacity)),P&&Object.hasOwn(P,"visible")&&(_.add(C),R===0&&P.visible===!1&&m.add(C))}for(let[C,P]of D.deformations){if(x.add(C),P.braid&&v.add(C),a!=="morph")continue;let T=y.get(C);if(!T)T={rest:P,samples:[]},y.set(C,T);else if(!Ho(T.rest,P))throw new Error(`clip ${t.id} changes the REST path of ${C} at ${L.toFixed(4)}s, so its geometry has no single base mesh for morph targets to be deltas against. Author one rest path per tube for the whole clip (move the tube with .translate/.rotate instead), or export the clip as video (cadgen step snapshot --animation ${t.id} --video)`);T.samples.push({index:E,timeSec:E/b.hz,deformation:P===T.rest?P:{...P,restSpec:T.rest.restSpec}})}}let S=[];for(let E of Js){let L=E==="opacity"?g:_;if(L.size){if(!r.has(E))throw new Error(`clip ${t.id} animates .${E}() on ${Ie(L)}, and glTF has no standard animated channel for it. Pass drop: ["${E}"] to bake the value at start into the file instead, or animate the occurrence's transform rather than its appearance`);S.push(`.${E}() is not an animated glTF channel: ${Ie(L)} carries its value at start, frozen for the whole clip`)}}if(x.size){if(a==="refuse")throw new Error(`clip ${t.id} deforms tube geometry on ${Ie(x)}: that is per-vertex motion, which a node transform cannot carry. Pass deform: "morph" to bake it as morph targets (bigger file, deformTolerance sets how close they track), deform: "rest" to ship those tubes at their rest shape knowing they do not move, or export the clip as video (cadgen step snapshot --animation ${t.id} --video)`);a==="morph"?v.size&&S.push(`${Ie(v)} carries a braid: the strand pattern is a shader, not geometry, so the exported cord has the right shape and motion and a smooth surface`):S.push(`deform: "rest" ships ${Ie(x)} at rest shape: the clip's tube deformation is per-vertex motion this file does not carry`)}let A=[...m].filter(E=>f.has(E));if(A.length){for(let E of A)f.delete(E);S.push(`${Ie(A)} moves in this clip and is hidden at start: dropping .visible() omits the occurrence from the file, and a node that is not there carries no motion`)}let M=new Float32Array(e.frameCount);for(let E=0;E<e.frameCount;E+=1)M[E]=E/e.fps;let w=[],I=new Map;for(let[E,L]of f){let D=new Float32Array(L.translations),R=new Float32Array(L.rotations),C=new Float32Array(L.scales),P=If(C,L.count);I.set(E,{translation:[D[0],D[1],D[2]],rotation:[R[0],R[1],R[2],R[3]],scale:P?null:[C[0],C[1],C[2]]});let T={node:E};Ks(D,3,L.count)&&(T.translation=D),Ks(R,4,L.count)&&(T.rotation=R),!P&&Ks(C,3,L.count)&&(T.scale=C),(T.translation||T.rotation||T.scale)&&w.push(T)}return w.sort(oa),{name:t.id,times:M,channels:w,rest:I,statics:{opacity:d,hidden:m},deformations:y,grid:b,warnings:S}}p(ra,"sampleClipAnimation");function oa(i,t){return i.node!==t.node?i.node<t.node?-1:1:(i.weights?1:0)-(t.weights?1:0)}p(oa,"compareChannels");function aa(i,t){return t?.length?{...i,channels:[...i.channels,...t].sort(oa)}:i}p(aa,"withMorphChannels");function ca(i,t){let e=i.channels.map(s=>s.node).filter(s=>!t.has(s));if(!e.length)return i;let n=new Map;for(let[s,r]of i.rest)t.has(s)&&n.set(s,r);return{...i,channels:i.channels.filter(s=>t.has(s.node)),rest:n,warnings:[...i.warnings,`${Ie(e)} moves in this clip but has no geometry in the export, so the file carries no node to animate for it`]}}p(ca,"restrictAnimationToNodes");var Si={BufferGeometry:We,Float32BufferAttribute:ue,Matrix3:Y,Vector3:V},Pf=1,Qs=512*1024*1024,la=16,ua=5,Lf=128,Nf=512,Ai=new gt;function ha(i,t=6){let e=[...i].sort();return e.length<=t?e.join(", "):`${e.slice(0,t).join(", ")} (and ${e.length-t} more)`}p(ha,"summarize");function fa(i){return i>=1024**3?`${(i/1024**3).toFixed(2)} GiB`:`${(i/1024**2).toFixed(1)} MiB`}p(fa,"formatBytes");function Df(i,t){let e=Array.isArray(i.transform)?i.transform:null,n=e===null||Hs(e),s=!n&&Vs(e)<0,r=n?null:Gs(e),o=t.positions,a=t.normals,c=Math.floor(o.length/3),l=new Float32Array(o.length),u=new Float32Array(o.length);for(let y=0;y<c;y+=1){let v=y*3;n?(l[v]=o[v],l[v+1]=o[v+1],l[v+2]=o[v+2]):ks(e,o[v],o[v+1],o[v+2],l,v);let b=a[v],S=a[v+1],A=a[v+2],M=b,w=S,I=A;r&&(M=r[0]*b+r[1]*S+r[2]*A,w=r[3]*b+r[4]*S+r[5]*A,I=r[6]*b+r[7]*S+r[8]*A);let E=Math.hypot(M,w,I)||1;u[v]=M/E,u[v+1]=w/E,u[v+2]=I/E}let h=t.faceRanges||[],f=0;for(let y of h)f+=Math.floor((Number(y.indexCount)||0)/3);let d=new Uint32Array(f*3),m=new Uint32Array(f),g=s?[0,2,1]:[0,1,2],_=0;h.forEach((y,v)=>{let b=Number(y.indexStart)||0,S=Number(y.indexCount)||0;for(let A=b;A+2<b+S;A+=3)d[_*3]=t.indices[A+g[0]],d[_*3+1]=t.indices[A+g[1]],d[_*3+2]=t.indices[A+g[2]],m[_]=v,_+=1});let x=new We;return x.setAttribute("position",new Nt(l,3)),x.setAttribute("normal",new Nt(u,3)),x.setIndex(new Nt(d,1)),{geometry:x,triangleRange:m}}p(Df,"occurrenceWorldGeometry");function Uf(i){let t=i.values,e=Math.floor(t.length/8),n=new Map;for(let a=0;a<e;a+=1){let c=a*8,l=t[c],u=n.get(l);if(!u){n.set(l,[t[c+1],t[c+1],t[c+2],t[c+2],t[c+3],t[c+3]]);continue}for(let h=0;h<3;h+=1){let f=t[c+1+h];f<u[h*2]&&(u[h*2]=f),f>u[h*2+1]&&(u[h*2+1]=f)}}let s=[...n.keys()].sort((a,c)=>a-c),r=new Uint32Array(s.length+1),o=[];return s.forEach((a,c)=>{let l=n.get(a),u=[0,1,2].map(h=>l[h*2]===l[h*2+1]?[l[h*2]]:[l[h*2],l[h*2+1]]);for(let h of u[0])for(let f of u[1])for(let d of u[2])o.push(h,f,d);r[c+1]=o.length/3}),{fractions:Float64Array.from(s),cornerOffset:r,uva:Float64Array.from(o)}}p(Uf,"boundsForFractions");function da(i,t,e){let n=t.path,s=(t.twistDeg||0)*Math.PI/180,r=Math.cos(s),o=Math.sin(s);for(let a=0;a<i.fractions.length;a+=1){let c=yi(n,i.fractions[a]*n.length),l=c.point,u=c.normal,h=c.binormal,f=c.tangent;for(let d=i.cornerOffset[a];d<i.cornerOffset[a+1];d+=1){let m=d*3,g=i.uva[m],_=i.uva[m+1],x=i.uva[m+2],y=r*g-o*_,v=o*g+r*_;e[m]=l[0]+u[0]*y+h[0]*v+f[0]*x,e[m+1]=l[1]+u[1]*y+h[1]*v+f[1]*x,e[m+2]=l[2]+u[2]*y+h[2]*v+f[2]*x}}return e}p(da,"poseCorners");function Ff(i,t,e,n){let s=0;for(let r=0;r<e.length;r+=3){let o=e[r]-(i[r]+(t[r]-i[r])*n),a=e[r+1]-(i[r+1]+(t[r+1]-i[r+1])*n),c=e[r+2]-(i[r+2]+(t[r+2]-i[r+2])*n),l=o*o+a*a+c*c;l>s&&(s=l)}return Math.sqrt(s)}p(Ff,"blendDeviation");function Of(i,t,e){let n=i.length,s=[0];if(n<2)return s;let r=0,o=da(t,Re(i[0]),new Float64Array(t.uva.length)),a=o,c=[],l=!0;for(let u=1;u<n;u+=1){let h=vi(i[u],i[u-1])?a:da(t,Re(i[u]),new Float64Array(t.uva.length));a=h,c.push({index:u,pose:h}),l=l&&vi(i[u],i[r]);let f=!1;if(!l){let g=u-r;for(let _ of c){if(_.index===u)continue;let x=(_.index-r)/g;if(Ff(o,h,_.pose,x)>e){f=!0;break}}}if(!f&&c.length<Lf)continue;let d=f?u-1:u,m=c.find(g=>g.index===d);s.push(d),r=d,o=m.pose,c=c.filter(g=>g.index>d),l=c.every(g=>vi(i[g.index],i[r]))}return s[s.length-1]!==n-1&&s.push(n-1),s}p(Of,"fitTargetTimes");function Bf(i,t,e){let n=i.geometry.index,s=Math.floor(n.count/3),r=i.sourceTriangles,o=new Map;for(let a=0;a<s;a+=1){let c=r?r[a]:a,l=e[t[c]]||e[0],u=o.get(l);u||o.set(l,u=[]),u.push(a)}return[...o.entries()].map(([a,c])=>{let l=new Uint32Array(c.length*3),u=new Map,h=0;c.forEach((d,m)=>{for(let g=0;g<3;g+=1){let _=n.getX(d*3+g),x=u.get(_);x===void 0&&(x=h,h+=1,u.set(_,x)),l[m*3+g]=x}});let f=new Uint32Array(h);for(let[d,m]of u)f[m]=d;return{color:a,indices:l,vertexIds:f,slotOf:u}})}p(Bf,"partitionByColor");function In(i,t){let e=new Float32Array(t.length*3);for(let n=0;n<t.length;n+=1){let s=t[n]*3;e[n*3]=i[s],e[n*3+1]=i[s+1],e[n*3+2]=i[s+2]}return e}p(In,"gather");function zf(i){let t=Math.max(1,Math.min(i,Nf)),e=new Uint32Array(t);for(let n=0;n<t;n+=1)e[n]=Math.floor(n*i/t);return e}p(zf,"verifySampleIds");function kf(i,t){let e=0;for(let n=0;n<i.length;n+=3){let s=i[n],r=i[n+1],o=i[n+2],a=t[n],c=t[n+1],l=t[n+2],u=Math.hypot(s,r,o)*Math.hypot(a,c,l);if(u<1e-12)continue;let h=Math.min(1,Math.max(-1,(s*a+r*c+o*l)/u)),f=Math.acos(h)*180/Math.PI;f>e&&(e=f)}return e}p(kf,"maxNormalDegrees");function pa(i,t,e,n={}){let{toleranceMm:s=Pf,grid:r,defaultColor:o=null,clipId:a="clip",maxRuntimeBytes:c=Qs}=n,l=Number(s);if(!(l>0))throw new Error(`morph deformTolerance must be a positive number of millimetres, got ${s}`);let u=[],h=new Map,f=[];if(!e?.size)return{overrides:h,channels:f,warnings:u,stats:null};let d=[],m=[];for(let y of i.occurrences||[]){let v=String(y.component||""),b=String(y.id||v),S=e.get(b);if(!S)continue;let A=t.get(v);if(!A||!A.positions?.length){m.push(b);continue}d.push({occurrence:y,occurrenceId:b,tessellation:A,entry:S})}if(m.length&&u.push(`${ha(m)} deforms in this clip but tessellated to nothing, so the file carries no geometry to morph for it`),!d.length)return{overrides:h,channels:f,warnings:u,stats:null};let g=[],_=0;for(let y of d){let v=y.entry.samples[0].deformation,{geometry:b,triangleRange:S}=Df(y.occurrence,y.tessellation),A=Xo(Si,b,Re(v),Ai),M={restSpec:v.restSpec,pathSpec:v.restSpec,twistDeg:0,maxSegmentLength:v.maxSegmentLength,braid:v.braid},w=new Array(r.count).fill(M);for(let D of y.entry.samples)w[D.index]=D.deformation;let I=Uf(A.mapping),E=Of(w,I,l),L=A.vertexCount;g.push({...y,bake:A,model:I,poses:w,keys:E,triangleRange:S,vertexCount:L}),_+=L*Math.max(0,E.length-1)*2*la}if(_>Math.min(c,Qs)){let y=g.reduce((b,S)=>b+Math.max(0,S.keys.length-1),0),v=g.reduce((b,S)=>b+S.vertexCount,0);throw new Error(`clip ${a} needs ${y} morph targets over ${g.length} tubes (${v} refined vertices) to hold ${l}mm, which is ${fa(_)} of morph texture at playback \u2014 past the ${fa(Math.min(c,Qs))} ceiling, and it is the GPU number rather than the file size that decides whether the file opens. Raise deformTolerance (the target count falls as its square root), shorten seconds, coarsen --mesh-tolerance so the tubes carry fewer vertices, or coarsen the clip's own maxSegmentLength`)}let x={toleranceMm:l,nodes:0,targets:0,bytes:0,runtimeBytes:0,refinedTriangles:0,deviationMm:0,normalsOmitted:[]};for(let y of g){let{bake:v,poses:b,keys:S,vertexCount:A,occurrenceId:M}=y,w=new ue(new Float32Array(A*3),3),I=new ue(new Float32Array(A*3),3);Mi(Si,v,Re(b[S[0]]),Ai,w,I);let E=Float32Array.from(w.array),L=Float32Array.from(I.array),D=zf(A),R=[],C=[],P=[],T=0;for(let B=1;B<S.length;B+=1){Mi(Si,v,Re(b[S[B]]),Ai,w,I);let W=new Float32Array(A*3),q=new Float32Array(A*3);for(let $=0;$<W.length;$+=1)W[$]=w.array[$]-E[$],q[$]=I.array[$]-L[$];R.push(W),C.push(q),P.push(In(w.array,D)),T=Math.max(T,kf(L,I.array))}let U=T>=ua;!U&&R.length&&x.normalsOmitted.push(M);let F=new Int32Array(S.length).fill(-1),N=[];for(let B=1;B<S.length;B+=1){let W=R[B-1],q=!1;for(let $=0;$<W.length;$+=1)if(W[$]!==0){q=!0;break}q&&(F[B]=N.length,N.push(B-1))}let O=Vf(y,{basePositions:E,deltaPositions:R,grid:r,tolerance:l,posed:w,posedNormals:I});x.deviationMm=Math.max(x.deviationMm,O);let k=Io(i,y.occurrence,y.tessellation,o||void 0),z=zs(y.occurrence.material),X=Bf(v,y.triangleRange,k).map(B=>{let W=B.vertexIds,q=N.map(K=>({positionDeltas:In(R[K],W),...U?{normalDeltas:In(C[K],W)}:{}})),$=[],J=[];return D.forEach((K,Q)=>{let nt=B.slotOf.get(K);nt!==void 0&&($.push(nt),J.push(Q))}),{color:B.color,positions:In(E,W),normals:In(L,W),indices:B.indices,...z===null?{}:{material:z},...q.length?{targets:q}:{},...q.length&&$.length?{verify:{vertexIds:Uint32Array.from($),posed:N.map(K=>{let Q=P[K],nt=new Float32Array(J.length*3);return J.forEach((yt,Jt)=>{nt[Jt*3]=Q[yt*3],nt[Jt*3+1]=Q[yt*3+1],nt[Jt*3+2]=Q[yt*3+2]}),nt})}}:{}}});h.set(M,X),x.nodes+=1,x.targets+=N.length,x.refinedTriangles+=Math.floor(v.geometry.index.count/3);for(let B of X){let W=B.positions.length/3;x.bytes+=W*N.length*(U?24:12),x.runtimeBytes+=W*N.length*(U?2:1)*la}if(N.length){let B=new Float32Array(S.length),W=new Float32Array(S.length*N.length);for(let q=0;q<S.length;q+=1)B[q]=S[q]/r.hz,F[q]>=0&&(W[q*N.length+F[q]]=1);f.push({node:M,times:B,weights:W,targetCount:N.length})}}return x.normalsOmitted.length&&u.push(`${ha(x.normalsOmitted)} turns by less than ${ua}\xB0 over this clip, so its morph targets carry positions only and its shading rides the base normals`),{overrides:h,channels:f,warnings:u,stats:x}}p(pa,"buildTubeMorphTargets");function Vf(i,{basePositions:t,deltaPositions:e,grid:n,tolerance:s,posed:r,posedNormals:o}){let{bake:a,poses:c,keys:l,occurrenceId:u}=i;if(l.length<2)return 0;let h=0,f=0;for(let d=0;d<c.length;d+=n.multiple){for(;f+2<l.length&&l[f+1]<=d;)f+=1;let m=l[f],g=l[f+1],_=g===m?0:(d-m)/(g-m);Mi(Si,a,Re(c[d]),Ai,r,o);let x=f>=1?e[f-1]:null,y=e[f];for(let v=0;v<t.length;v+=3){let b=0;for(let S=0;S<3;S+=1){let A=t[v+S]+(x?x[v+S]*(1-_):0)+(y?y[v+S]*_:0),M=r.array[v+S]-A;b+=M*M}b>h&&(h=b)}}if(h=Math.sqrt(h),h>s+.001)throw new Error(`morph fit for ${u} leaves ${h.toFixed(4)}mm between the baked targets and the clip's own deformation, past the ${s}mm it was fitted to`);return h}p(Vf,"verifyMorphFit");var tr=Object.freeze(["clips"]);function Gf(i){if(typeof Buffer<"u")return Buffer.from(i,"utf8").toString("base64");let t=new TextEncoder().encode(i),e="";for(let n of t)e+=String.fromCharCode(n);return btoa(e)}p(Gf,"base64Utf8");async function Hf(i,{name:t="embedded animation"}={}){let e=String(i||""),n=`data:text/javascript;base64,${Gf(e)}`;try{return await import(n)}catch(s){let r=s instanceof Error?s.message:String(s);throw new Error(`${t}: ${r}`)}}p(Hf,"importAnimationModule");function Wf(i,{name:t="embedded animation"}={}){let n=Object.keys(i||{}).filter(s=>s!=="default").filter(s=>!tr.includes(s));if(n.length)throw new Error(`${t}: unknown export${n.length===1?"":"s"} ${n.join(", ")} \u2014 the renderer understands: ${tr.join(", ")}`);if("default"in(i||{}))throw new Error(`${t}: a default export is not an animation-module export \u2014 use named exports (${tr.join(", ")})`);return{clips:$o(i?.clips)}}p(Wf,"compileAnimationModule");async function ma(i,t={}){let e=await Hf(i,t);return Wf(e,t)}p(ma,"compileAnimationSource");function Xf(i){let t={},e=[],n=[],s=[],r=[],o={chord:void 0,angle:void 0};for(let a=0;a<i.length;a+=1){let c=i[a];if(!c.startsWith("--"))continue;let l=i[a+1],u=l===void 0||l.startsWith("--")?"true":l;u!=="true"&&(a+=1),c==="--format"?(e.push(u),s.push({chord:void 0,angle:void 0}),r.push(void 0)):c==="--out"?n.push(u):c==="--chord-tolerance"?(s.length?s[s.length-1]:o).chord=u:c==="--angle-tolerance"?(s.length?s[s.length-1]:o).angle=u:c==="--animation"?(r.length||Ct("--animation must follow the --format/--out pair it animates"),r[r.length-1]=u):t[c.slice(2)]=u}return{args:t,formats:e,outs:n,pairTolerances:s,pairAnimations:r,defaults:o}}p(Xf,"parseArgs");function Ct(i){process.stdout.write(`${JSON.stringify({ok:!1,error:String(i)})}
`),process.exit(1)}p(Ct,"fail");function qf(i,t,e,n){let s=String(e?.surfaceInput||""),r=String(e?.surfaceObject||""),o=Ae(s,n),a=ao(Is(o),{surfaceInput:s,surfaceObject:r,tessellationInput:o,tessellation:n});if(a)return{...a.component,partColor:a.partColor};let c=String(e?.surf||"");if(!c)throw new Error(`component ${t} has no surf payload`);let l=nn.readFileSync(sn.join(i,c)),{index:u,floats:h}=sr(l.buffer.slice(l.byteOffset,l.byteOffset+l.byteLength)),f=bs(u,h,n),d=Array.isArray(u.partColor)?u.partColor:null;return mo(o,so(f,{surfaceInput:s,surfaceObject:r,tessellation:n,partColor:d,edgeClasses:io(u)})),{...f,partColor:d}}p(qf,"tessellationForComponent");var{args:Pn,formats:er,outs:ya,pairTolerances:ga,pairAnimations:xa,defaults:_a}=Xf(process.argv.slice(2)),wi=String(Pn["package-dir"]||"");(!wi||!sn.isAbsolute(wi))&&Ct("--package-dir must be an absolute render-package directory");(!er.length||er.length!==ya.length)&&Ct("--format and --out must be given as one or more ordered pairs");var Pe=er.map((i,t)=>{let e=ga[t].chord??_a.chord,n=ga[t].angle??_a.angle,s={...Vt};e!==void 0&&(s.chordTolerance=Number(e)),n!==void 0&&(s.angleTolerance=Number(n));let r=null;if(xa[t]!==void 0){try{r=JSON.parse(String(xa[t]))}catch(o){Ct(`--animation must be a JSON object: ${o?.message||o}`)}(!r||typeof r!="object"||Array.isArray(r))&&Ct("--animation must be a JSON object")}return{format:String(i).toLowerCase(),out:String(ya[t]),options:s,animation:r,groupKey:`${s.chordTolerance}:${s.angleTolerance}`}});for(let i of Pe)(!i.out||!sn.isAbsolute(i.out))&&Ct("--out must be an absolute output path"),Bs.includes(i.format)||Ct(`--format must be one of ${Bs.join(", ")}`),(!(i.options.chordTolerance>0)||!(i.options.angleTolerance>0))&&Ct("tolerances must be positive numbers"),i.animation&&i.format!=="glb"&&Ct(`${i.format} carries no animation: only glb does`),i.animation&&!String(i.animation.clip||"").trim()&&Ct("--animation must name a clip");new Set(Pe.map(i=>i.out)).size!==Pe.length&&Ct("--out paths must be distinct");var $f=String(Pn.name||sn.basename(Pe[0].out).replace(/\.[^.]+$/,"")||"model"),Ti=Pn["default-color"]?String(Pn["default-color"]):null;Ti!==null&&!/^#[0-9a-fA-F]{6}$/.test(Ti)&&Ct("--default-color must be #rrggbb");var va=String(Pn["animation-source"]||"");Pe.some(i=>i.animation)&&!va&&Ct("--animation needs --animation-source: the clips live in the document sidecar");async function Yf(i){let t=nn.readFileSync(i,"utf8");return(await ma(t,{name:"embedded animation"})).clips}p(Yf,"loadClips");function Zf(i,t,e){let n=String(i.animation.clip),s=Zo(t,n);if(!s){let a=Yo(t).map(c=>c.id);throw new Error(a.length?`Unknown animation clip: ${n}. This model declares: ${a.join(", ")}`:`Unknown animation clip: ${n}. This model declares no animation clips`)}let r=Qo(i.animation,s,{label:"animation"}),o=ra(e,s,r,{drop:Array.isArray(i.animation.drop)?i.animation.drop:[],deform:i.animation.deform});return{clip:s,plan:r,sampled:o}}p(Zf,"sampleJobAnimation");try{let i=JSON.parse(nn.readFileSync(sn.join(wi,"assembly.json"),"utf8")),t=i.components||{},e=new Set((i.occurrences||[]).map(o=>String(o.component||""))),n=Pe.some(o=>o.animation)?await Yf(va):null,s=new Map;Pe.forEach((o,a)=>{s.has(o.groupKey)||s.set(o.groupKey,{options:o.options,members:[]}),s.get(o.groupKey).members.push({job:o,index:a})});let r=[];for(let o of s.values()){let a=new Map;for(let u of e){if(!t[u])throw new Error(`descriptor names unknown component ${u}`);a.set(u,qf(wi,u,t[u],o.options))}let c=Ti?{defaultColor:Ti.toLowerCase()}:{},l=null;for(let{job:u,index:h}of o.members){let f,d=null,m=null;if(u.animation){let{plan:x,sampled:y}=Zf(u,n,i),v=pa(i,a,y.deformations,{toleranceMm:u.animation.deformTolerance,grid:y.grid,clipId:y.name,...c.defaultColor?{defaultColor:c.defaultColor}:{}});f=Ws(i,a,{...c,perOccurrence:!0,hiddenOccurrenceIds:y.statics.hidden,occurrenceOpacity:y.statics.opacity,occurrenceOverrides:v.overrides}),d=ca(aa(y,v.channels),new Set(f.primitives.map(b=>b.node).filter(Boolean))),m={clip:d.name,fps:x.fps,samples:x.frameCount,seconds:x.seconds,start:x.start,channels:d.channels.length,...v.stats?{deform:{mode:"morph",nodes:v.stats.nodes,targets:v.stats.targets,bytes:v.stats.bytes,runtimeBytes:v.stats.runtimeBytes,refinedTriangles:v.stats.refinedTriangles,deviationMm:Number(v.stats.deviationMm.toFixed(4)),toleranceMm:v.stats.toleranceMm,fitGridHz:y.grid.hz}}:{},warnings:[...x.warnings,...d.warnings,...v.warnings]}}else l=l||Ws(i,a,c),f=l;if(!f.triangleCount)throw new Error("tree produced no triangles");let{body:g}=Po(f,u.format,{name:$f,animation:d});nn.mkdirSync(sn.dirname(u.out),{recursive:!0});let _=`${u.out}.${process.pid}.tmp`;nn.writeFileSync(_,g),nn.renameSync(_,u.out),r[h]={path:u.out,format:u.format,triangleCount:f.triangleCount,...m?{animation:m}:{}}}}process.stdout.write(`${JSON.stringify({ok:!0,files:r})}
`)}catch(i){Ct(i?.message||i)}
/*! Bundled license information:

three/build/three.core.js:
three/build/three.module.js:
  (**
   * @license
   * Copyright 2010-2026 Three.js Authors
   * SPDX-License-Identifier: MIT
   *)
*/
