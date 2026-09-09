#!/usr/bin/env node
var $o=Object.defineProperty;var p=(i,t)=>$o(i,"name",{value:t,configurable:!0});import Ke from"node:fs";import we from"node:path";function ks(i){let t=new DataView(i,0,12);if(t.getUint32(0,!0)!==1179800915)throw new Error("not a SURF container");let e=t.getUint32(4,!0);if(e!==2)throw new Error(`unsupported SURF version ${e}`);let n=t.getUint32(8,!0),s=new Uint8Array(i,12,n),r=JSON.parse(new TextDecoder().decode(s)),o=12+n,a=new Float32Array(i.slice(o,o+(i.byteLength-o>>2<<2)));return{index:r,floats:a}}p(ks,"parseSurf");function jt(i,t){let[e,n]=t;return i.subarray(e,e+n)}p(jt,"floatSpan");var nr=1;var ir=3;var Ti=0,Ei=1,Ci=2,Ri=3,Ii=4,Pi=5,Li=6,Ni=7,sr=0,rr=1,or=2;var Ki=1,ji=2,Qi=3,ts=4,es=5,ns=6,is=7;var ss=300,ar=301,rs=302;var cr=306,Di=1e3,rn=1001,Ui=1002;var lr=1006;var hr=1008;var ur=1009;var fr=1015;var dr=1023;var cn=2300,Fn=2301,Dn=2302,Fi=2303,Oi=2400,Bi=2401,zi=2402;var os="",Ot="srgb",ki="srgb-linear",Vi="linear",Un="srgb";var Gi=35044;var on=2e3,Hi=2001;function Yo(i){for(let t=i.length-1;t>=0;--t)if(i[t]>=65535)return!0;return!1}p(Yo,"arrayNeedsUint32");function Zo(i){return ArrayBuffer.isView(i)&&!(i instanceof DataView)}p(Zo,"isTypedArray");function Wi(i){return document.createElementNS("http://www.w3.org/1999/xhtml",i)}p(Wi,"createElementNS");var Vs={},On=null;function pr(i){let t=i[0];if(typeof t=="string"&&t.startsWith("TSL:")){let e=i[1];e&&e.isStackTrace?i[0]+=" "+e.getLocation():i[1]='Stack trace not available. Enable "THREE.Node.captureStackTrace" to capture stack traces.'}return i}p(pr,"enhanceLogMessage");function dt(...i){i=pr(i);let t="THREE."+i.shift();if(On)On("warn",t,...i);else{let e=i[0];e&&e.isStackTrace?console.warn(e.getError(t)):console.warn(t,...i)}}p(dt,"warn");function st(...i){i=pr(i);let t="THREE."+i.shift();if(On)On("error",t,...i);else{let e=i[0];e&&e.isStackTrace?console.error(e.getError(t)):console.error(t,...i)}}p(st,"error");function Fe(...i){let t=i.join(" ");t in Vs||(Vs[t]=!0,dt(...i))}p(Fe,"warnOnce");var Jo={[Ti]:Ei,[Ci]:Li,[Ii]:Ni,[Ri]:Pi,[Ei]:Ti,[Li]:Ci,[Ni]:Ii,[Pi]:Ri},me=class{static{p(this,"EventDispatcher")}addEventListener(t,e){this._listeners===void 0&&(this._listeners={});let n=this._listeners;n[t]===void 0&&(n[t]=[]),n[t].indexOf(e)===-1&&n[t].push(e)}hasEventListener(t,e){let n=this._listeners;return n===void 0?!1:n[t]!==void 0&&n[t].indexOf(e)!==-1}removeEventListener(t,e){let n=this._listeners;if(n===void 0)return;let s=n[t];if(s!==void 0){let r=s.indexOf(e);r!==-1&&s.splice(r,1)}}dispatchEvent(t){let e=this._listeners;if(e===void 0)return;let n=e[t.type];if(n!==void 0){t.target=this;let s=n.slice(0);for(let r=0,o=s.length;r<o;r++)s[r].call(this,t);t.target=null}}},vt=["00","01","02","03","04","05","06","07","08","09","0a","0b","0c","0d","0e","0f","10","11","12","13","14","15","16","17","18","19","1a","1b","1c","1d","1e","1f","20","21","22","23","24","25","26","27","28","29","2a","2b","2c","2d","2e","2f","30","31","32","33","34","35","36","37","38","39","3a","3b","3c","3d","3e","3f","40","41","42","43","44","45","46","47","48","49","4a","4b","4c","4d","4e","4f","50","51","52","53","54","55","56","57","58","59","5a","5b","5c","5d","5e","5f","60","61","62","63","64","65","66","67","68","69","6a","6b","6c","6d","6e","6f","70","71","72","73","74","75","76","77","78","79","7a","7b","7c","7d","7e","7f","80","81","82","83","84","85","86","87","88","89","8a","8b","8c","8d","8e","8f","90","91","92","93","94","95","96","97","98","99","9a","9b","9c","9d","9e","9f","a0","a1","a2","a3","a4","a5","a6","a7","a8","a9","aa","ab","ac","ad","ae","af","b0","b1","b2","b3","b4","b5","b6","b7","b8","b9","ba","bb","bc","bd","be","bf","c0","c1","c2","c3","c4","c5","c6","c7","c8","c9","ca","cb","cc","cd","ce","cf","d0","d1","d2","d3","d4","d5","d6","d7","d8","d9","da","db","dc","dd","de","df","e0","e1","e2","e3","e4","e5","e6","e7","e8","e9","ea","eb","ec","ed","ee","ef","f0","f1","f2","f3","f4","f5","f6","f7","f8","f9","fa","fb","fc","fd","fe","ff"];var mf=Math.PI/180,Ko=180/Math.PI;function ti(){let i=Math.random()*4294967295|0,t=Math.random()*4294967295|0,e=Math.random()*4294967295|0,n=Math.random()*4294967295|0;return(vt[i&255]+vt[i>>8&255]+vt[i>>16&255]+vt[i>>24&255]+"-"+vt[t&255]+vt[t>>8&255]+"-"+vt[t>>16&15|64]+vt[t>>24&255]+"-"+vt[e&63|128]+vt[e>>8&255]+"-"+vt[e>>16&255]+vt[e>>24&255]+vt[n&255]+vt[n>>8&255]+vt[n>>16&255]+vt[n>>24&255]).toLowerCase()}p(ti,"generateUUID");function J(i,t,e){return Math.max(t,Math.min(e,i))}p(J,"clamp");function jo(i,t){return(i%t+t)%t}p(jo,"euclideanModulo");function gi(i,t,e){return(1-e)*i+e*t}p(gi,"lerp");function Qe(i,t){switch(t.constructor){case Float32Array:return i;case Uint32Array:return i/4294967295;case Uint16Array:return i/65535;case Uint8Array:return i/255;case Int32Array:return Math.max(i/2147483647,-1);case Int16Array:return Math.max(i/32767,-1);case Int8Array:return Math.max(i/127,-1);default:throw new Error("THREE.MathUtils: Invalid component type.")}}p(Qe,"denormalize");function wt(i,t){switch(t.constructor){case Float32Array:return i;case Uint32Array:return Math.round(i*4294967295);case Uint16Array:return Math.round(i*65535);case Uint8Array:return Math.round(i*255);case Int32Array:return Math.round(i*2147483647);case Int16Array:return Math.round(i*32767);case Int8Array:return Math.round(i*127);default:throw new Error("THREE.MathUtils: Invalid component type.")}}p(wt,"normalize");var pt=class i{static{p(this,"Vector2")}static{i.prototype.isVector2=!0}constructor(t=0,e=0){this.x=t,this.y=e}get width(){return this.x}set width(t){this.x=t}get height(){return this.y}set height(t){this.y=t}set(t,e){return this.x=t,this.y=e,this}setScalar(t){return this.x=t,this.y=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;default:throw new Error("THREE.Vector2: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;default:throw new Error("THREE.Vector2: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y)}copy(t){return this.x=t.x,this.y=t.y,this}add(t){return this.x+=t.x,this.y+=t.y,this}addScalar(t){return this.x+=t,this.y+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this}subScalar(t){return this.x-=t,this.y-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this}multiply(t){return this.x*=t.x,this.y*=t.y,this}multiplyScalar(t){return this.x*=t,this.y*=t,this}divide(t){return this.x/=t.x,this.y/=t.y,this}divideScalar(t){return this.multiplyScalar(1/t)}applyMatrix3(t){let e=this.x,n=this.y,s=t.elements;return this.x=s[0]*e+s[3]*n+s[6],this.y=s[1]*e+s[4]*n+s[7],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this}clamp(t,e){return this.x=J(this.x,t.x,e.x),this.y=J(this.y,t.y,e.y),this}clampScalar(t,e){return this.x=J(this.x,t,e),this.y=J(this.y,t,e),this}clampLength(t,e){let n=this.length();return this.divideScalar(n||1).multiplyScalar(J(n,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this}negate(){return this.x=-this.x,this.y=-this.y,this}dot(t){return this.x*t.x+this.y*t.y}cross(t){return this.x*t.y-this.y*t.x}lengthSq(){return this.x*this.x+this.y*this.y}length(){return Math.sqrt(this.x*this.x+this.y*this.y)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)}normalize(){return this.divideScalar(this.length()||1)}angle(){return Math.atan2(-this.y,-this.x)+Math.PI}angleTo(t){let e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;let n=this.dot(t)/e;return Math.acos(J(n,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){let e=this.x-t.x,n=this.y-t.y;return e*e+n*n}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this}lerpVectors(t,e,n){return this.x=t.x+(e.x-t.x)*n,this.y=t.y+(e.y-t.y)*n,this}equals(t){return t.x===this.x&&t.y===this.y}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this}rotateAround(t,e){let n=Math.cos(e),s=Math.sin(e),r=this.x-t.x,o=this.y-t.y;return this.x=r*n-o*s+t.x,this.y=r*s+o*n+t.y,this}random(){return this.x=Math.random(),this.y=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y}},Ht=class{static{p(this,"Quaternion")}constructor(t=0,e=0,n=0,s=1){this.isQuaternion=!0,this._x=t,this._y=e,this._z=n,this._w=s}static slerpFlat(t,e,n,s,r,o,a){let c=n[s+0],l=n[s+1],h=n[s+2],u=n[s+3],f=r[o+0],d=r[o+1],m=r[o+2],g=r[o+3];if(u!==g||c!==f||l!==d||h!==m){let _=c*f+l*d+h*m+u*g;_<0&&(f=-f,d=-d,m=-m,g=-g,_=-_);let x=1-a;if(_<.9995){let M=Math.acos(_),y=Math.sin(M);x=Math.sin(x*M)/y,a=Math.sin(a*M)/y,c=c*x+f*a,l=l*x+d*a,h=h*x+m*a,u=u*x+g*a}else{c=c*x+f*a,l=l*x+d*a,h=h*x+m*a,u=u*x+g*a;let M=1/Math.sqrt(c*c+l*l+h*h+u*u);c*=M,l*=M,h*=M,u*=M}}t[e]=c,t[e+1]=l,t[e+2]=h,t[e+3]=u}static multiplyQuaternionsFlat(t,e,n,s,r,o){let a=n[s],c=n[s+1],l=n[s+2],h=n[s+3],u=r[o],f=r[o+1],d=r[o+2],m=r[o+3];return t[e]=a*m+h*u+c*d-l*f,t[e+1]=c*m+h*f+l*u-a*d,t[e+2]=l*m+h*d+a*f-c*u,t[e+3]=h*m-a*u-c*f-l*d,t}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get w(){return this._w}set w(t){this._w=t,this._onChangeCallback()}set(t,e,n,s){return this._x=t,this._y=e,this._z=n,this._w=s,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._w)}copy(t){return this._x=t.x,this._y=t.y,this._z=t.z,this._w=t.w,this._onChangeCallback(),this}setFromEuler(t,e=!0){let n=t._x,s=t._y,r=t._z,o=t._order,a=Math.cos,c=Math.sin,l=a(n/2),h=a(s/2),u=a(r/2),f=c(n/2),d=c(s/2),m=c(r/2);switch(o){case"XYZ":this._x=f*h*u+l*d*m,this._y=l*d*u-f*h*m,this._z=l*h*m+f*d*u,this._w=l*h*u-f*d*m;break;case"YXZ":this._x=f*h*u+l*d*m,this._y=l*d*u-f*h*m,this._z=l*h*m-f*d*u,this._w=l*h*u+f*d*m;break;case"ZXY":this._x=f*h*u-l*d*m,this._y=l*d*u+f*h*m,this._z=l*h*m+f*d*u,this._w=l*h*u-f*d*m;break;case"ZYX":this._x=f*h*u-l*d*m,this._y=l*d*u+f*h*m,this._z=l*h*m-f*d*u,this._w=l*h*u+f*d*m;break;case"YZX":this._x=f*h*u+l*d*m,this._y=l*d*u+f*h*m,this._z=l*h*m-f*d*u,this._w=l*h*u-f*d*m;break;case"XZY":this._x=f*h*u-l*d*m,this._y=l*d*u-f*h*m,this._z=l*h*m+f*d*u,this._w=l*h*u+f*d*m;break;default:dt("Quaternion: .setFromEuler() encountered an unknown order: "+o)}return e===!0&&this._onChangeCallback(),this}setFromAxisAngle(t,e){let n=e/2,s=Math.sin(n);return this._x=t.x*s,this._y=t.y*s,this._z=t.z*s,this._w=Math.cos(n),this._onChangeCallback(),this}setFromRotationMatrix(t){let e=t.elements,n=e[0],s=e[4],r=e[8],o=e[1],a=e[5],c=e[9],l=e[2],h=e[6],u=e[10],f=n+a+u;if(f>0){let d=.5/Math.sqrt(f+1);this._w=.25/d,this._x=(h-c)*d,this._y=(r-l)*d,this._z=(o-s)*d}else if(n>a&&n>u){let d=2*Math.sqrt(1+n-a-u);this._w=(h-c)/d,this._x=.25*d,this._y=(s+o)/d,this._z=(r+l)/d}else if(a>u){let d=2*Math.sqrt(1+a-n-u);this._w=(r-l)/d,this._x=(s+o)/d,this._y=.25*d,this._z=(c+h)/d}else{let d=2*Math.sqrt(1+u-n-a);this._w=(o-s)/d,this._x=(r+l)/d,this._y=(c+h)/d,this._z=.25*d}return this._onChangeCallback(),this}setFromUnitVectors(t,e){let n=t.dot(e)+1;return n<1e-8?(n=0,Math.abs(t.x)>Math.abs(t.z)?(this._x=-t.y,this._y=t.x,this._z=0,this._w=n):(this._x=0,this._y=-t.z,this._z=t.y,this._w=n)):(this._x=t.y*e.z-t.z*e.y,this._y=t.z*e.x-t.x*e.z,this._z=t.x*e.y-t.y*e.x,this._w=n),this.normalize()}angleTo(t){return 2*Math.acos(Math.abs(J(this.dot(t),-1,1)))}rotateTowards(t,e){let n=this.angleTo(t);if(n===0)return this;let s=Math.min(1,e/n);return this.slerp(t,s),this}identity(){return this.set(0,0,0,1)}invert(){return this.conjugate()}conjugate(){return this._x*=-1,this._y*=-1,this._z*=-1,this._onChangeCallback(),this}dot(t){return this._x*t._x+this._y*t._y+this._z*t._z+this._w*t._w}lengthSq(){return this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w}length(){return Math.sqrt(this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w)}normalize(){let t=this.length();return t===0?(this._x=0,this._y=0,this._z=0,this._w=1):(t=1/t,this._x=this._x*t,this._y=this._y*t,this._z=this._z*t,this._w=this._w*t),this._onChangeCallback(),this}multiply(t){return this.multiplyQuaternions(this,t)}premultiply(t){return this.multiplyQuaternions(t,this)}multiplyQuaternions(t,e){let n=t._x,s=t._y,r=t._z,o=t._w,a=e._x,c=e._y,l=e._z,h=e._w;return this._x=n*h+o*a+s*l-r*c,this._y=s*h+o*c+r*a-n*l,this._z=r*h+o*l+n*c-s*a,this._w=o*h-n*a-s*c-r*l,this._onChangeCallback(),this}slerp(t,e){let n=t._x,s=t._y,r=t._z,o=t._w,a=this.dot(t);a<0&&(n=-n,s=-s,r=-r,o=-o,a=-a);let c=1-e;if(a<.9995){let l=Math.acos(a),h=Math.sin(l);c=Math.sin(c*l)/h,e=Math.sin(e*l)/h,this._x=this._x*c+n*e,this._y=this._y*c+s*e,this._z=this._z*c+r*e,this._w=this._w*c+o*e,this._onChangeCallback()}else this._x=this._x*c+n*e,this._y=this._y*c+s*e,this._z=this._z*c+r*e,this._w=this._w*c+o*e,this.normalize();return this}slerpQuaternions(t,e,n){return this.copy(t).slerp(e,n)}random(){let t=2*Math.PI*Math.random(),e=2*Math.PI*Math.random(),n=Math.random(),s=Math.sqrt(1-n),r=Math.sqrt(n);return this.set(s*Math.sin(t),s*Math.cos(t),r*Math.sin(e),r*Math.cos(e))}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._w===this._w}fromArray(t,e=0){return this._x=t[e],this._y=t[e+1],this._z=t[e+2],this._w=t[e+3],this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._w,t}fromBufferAttribute(t,e){return this._x=t.getX(e),this._y=t.getY(e),this._z=t.getZ(e),this._w=t.getW(e),this._onChangeCallback(),this}toJSON(){return this.toArray()}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._w}},k=class i{static{p(this,"Vector3")}static{i.prototype.isVector3=!0}constructor(t=0,e=0,n=0){this.x=t,this.y=e,this.z=n}set(t,e,n){return n===void 0&&(n=this.z),this.x=t,this.y=e,this.z=n,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;default:throw new Error("THREE.Vector3: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;default:throw new Error("THREE.Vector3: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this}multiplyVectors(t,e){return this.x=t.x*e.x,this.y=t.y*e.y,this.z=t.z*e.z,this}applyEuler(t){return this.applyQuaternion(Gs.setFromEuler(t))}applyAxisAngle(t,e){return this.applyQuaternion(Gs.setFromAxisAngle(t,e))}applyMatrix3(t){let e=this.x,n=this.y,s=this.z,r=t.elements;return this.x=r[0]*e+r[3]*n+r[6]*s,this.y=r[1]*e+r[4]*n+r[7]*s,this.z=r[2]*e+r[5]*n+r[8]*s,this}applyNormalMatrix(t){return this.applyMatrix3(t).normalize()}applyMatrix4(t){let e=this.x,n=this.y,s=this.z,r=t.elements,o=1/(r[3]*e+r[7]*n+r[11]*s+r[15]);return this.x=(r[0]*e+r[4]*n+r[8]*s+r[12])*o,this.y=(r[1]*e+r[5]*n+r[9]*s+r[13])*o,this.z=(r[2]*e+r[6]*n+r[10]*s+r[14])*o,this}applyQuaternion(t){let e=this.x,n=this.y,s=this.z,r=t.x,o=t.y,a=t.z,c=t.w,l=2*(o*s-a*n),h=2*(a*e-r*s),u=2*(r*n-o*e);return this.x=e+c*l+o*u-a*h,this.y=n+c*h+a*l-r*u,this.z=s+c*u+r*h-o*l,this}project(t){return this.applyMatrix4(t.matrixWorldInverse).applyMatrix4(t.projectionMatrix)}unproject(t){return this.applyMatrix4(t.projectionMatrixInverse).applyMatrix4(t.matrixWorld)}transformDirection(t){let e=this.x,n=this.y,s=this.z,r=t.elements;return this.x=r[0]*e+r[4]*n+r[8]*s,this.y=r[1]*e+r[5]*n+r[9]*s,this.z=r[2]*e+r[6]*n+r[10]*s,this.normalize()}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this}divideScalar(t){return this.multiplyScalar(1/t)}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this}clamp(t,e){return this.x=J(this.x,t.x,e.x),this.y=J(this.y,t.y,e.y),this.z=J(this.z,t.z,e.z),this}clampScalar(t,e){return this.x=J(this.x,t,e),this.y=J(this.y,t,e),this.z=J(this.z,t,e),this}clampLength(t,e){let n=this.length();return this.divideScalar(n||1).multiplyScalar(J(n,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this}lerpVectors(t,e,n){return this.x=t.x+(e.x-t.x)*n,this.y=t.y+(e.y-t.y)*n,this.z=t.z+(e.z-t.z)*n,this}cross(t){return this.crossVectors(this,t)}crossVectors(t,e){let n=t.x,s=t.y,r=t.z,o=e.x,a=e.y,c=e.z;return this.x=s*c-r*a,this.y=r*o-n*c,this.z=n*a-s*o,this}projectOnVector(t){let e=t.lengthSq();if(e===0)return this.set(0,0,0);let n=t.dot(this)/e;return this.copy(t).multiplyScalar(n)}projectOnPlane(t){return xi.copy(this).projectOnVector(t),this.sub(xi)}reflect(t){return this.sub(xi.copy(t).multiplyScalar(2*this.dot(t)))}angleTo(t){let e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;let n=this.dot(t)/e;return Math.acos(J(n,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){let e=this.x-t.x,n=this.y-t.y,s=this.z-t.z;return e*e+n*n+s*s}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)+Math.abs(this.z-t.z)}setFromSpherical(t){return this.setFromSphericalCoords(t.radius,t.phi,t.theta)}setFromSphericalCoords(t,e,n){let s=Math.sin(e)*t;return this.x=s*Math.sin(n),this.y=Math.cos(e)*t,this.z=s*Math.cos(n),this}setFromCylindrical(t){return this.setFromCylindricalCoords(t.radius,t.theta,t.y)}setFromCylindricalCoords(t,e,n){return this.x=t*Math.sin(e),this.y=n,this.z=t*Math.cos(e),this}setFromMatrixPosition(t){let e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this}setFromMatrixScale(t){let e=this.setFromMatrixColumn(t,0).length(),n=this.setFromMatrixColumn(t,1).length(),s=this.setFromMatrixColumn(t,2).length();return this.x=e,this.y=n,this.z=s,this}setFromMatrixColumn(t,e){return this.fromArray(t.elements,e*4)}setFromMatrix3Column(t,e){return this.fromArray(t.elements,e*3)}setFromEuler(t){return this.x=t._x,this.y=t._y,this.z=t._z,this}setFromColor(t){return this.x=t.r,this.y=t.g,this.z=t.b,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this}randomDirection(){let t=Math.random()*Math.PI*2,e=Math.random()*2-1,n=Math.sqrt(1-e*e);return this.x=n*Math.cos(t),this.y=e,this.z=n*Math.sin(t),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z}},xi=new k,Gs=new Ht,Y=class i{static{p(this,"Matrix3")}static{i.prototype.isMatrix3=!0}constructor(t,e,n,s,r,o,a,c,l){this.elements=[1,0,0,0,1,0,0,0,1],t!==void 0&&this.set(t,e,n,s,r,o,a,c,l)}set(t,e,n,s,r,o,a,c,l){let h=this.elements;return h[0]=t,h[1]=s,h[2]=a,h[3]=e,h[4]=r,h[5]=c,h[6]=n,h[7]=o,h[8]=l,this}identity(){return this.set(1,0,0,0,1,0,0,0,1),this}copy(t){let e=this.elements,n=t.elements;return e[0]=n[0],e[1]=n[1],e[2]=n[2],e[3]=n[3],e[4]=n[4],e[5]=n[5],e[6]=n[6],e[7]=n[7],e[8]=n[8],this}extractBasis(t,e,n){return t.setFromMatrix3Column(this,0),e.setFromMatrix3Column(this,1),n.setFromMatrix3Column(this,2),this}setFromMatrix4(t){let e=t.elements;return this.set(e[0],e[4],e[8],e[1],e[5],e[9],e[2],e[6],e[10]),this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){let n=t.elements,s=e.elements,r=this.elements,o=n[0],a=n[3],c=n[6],l=n[1],h=n[4],u=n[7],f=n[2],d=n[5],m=n[8],g=s[0],_=s[3],x=s[6],M=s[1],y=s[4],v=s[7],b=s[2],A=s[5],w=s[8];return r[0]=o*g+a*M+c*b,r[3]=o*_+a*y+c*A,r[6]=o*x+a*v+c*w,r[1]=l*g+h*M+u*b,r[4]=l*_+h*y+u*A,r[7]=l*x+h*v+u*w,r[2]=f*g+d*M+m*b,r[5]=f*_+d*y+m*A,r[8]=f*x+d*v+m*w,this}multiplyScalar(t){let e=this.elements;return e[0]*=t,e[3]*=t,e[6]*=t,e[1]*=t,e[4]*=t,e[7]*=t,e[2]*=t,e[5]*=t,e[8]*=t,this}determinant(){let t=this.elements,e=t[0],n=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],h=t[8];return e*o*h-e*a*l-n*r*h+n*a*c+s*r*l-s*o*c}invert(){let t=this.elements,e=t[0],n=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],h=t[8],u=h*o-a*l,f=a*c-h*r,d=l*r-o*c,m=e*u+n*f+s*d;if(m===0)return this.set(0,0,0,0,0,0,0,0,0);let g=1/m;return t[0]=u*g,t[1]=(s*l-h*n)*g,t[2]=(a*n-s*o)*g,t[3]=f*g,t[4]=(h*e-s*c)*g,t[5]=(s*r-a*e)*g,t[6]=d*g,t[7]=(n*c-l*e)*g,t[8]=(o*e-n*r)*g,this}transpose(){let t,e=this.elements;return t=e[1],e[1]=e[3],e[3]=t,t=e[2],e[2]=e[6],e[6]=t,t=e[5],e[5]=e[7],e[7]=t,this}getNormalMatrix(t){return this.setFromMatrix4(t).invert().transpose()}transposeIntoArray(t){let e=this.elements;return t[0]=e[0],t[1]=e[3],t[2]=e[6],t[3]=e[1],t[4]=e[4],t[5]=e[7],t[6]=e[2],t[7]=e[5],t[8]=e[8],this}setUvTransform(t,e,n,s,r,o,a){let c=Math.cos(r),l=Math.sin(r);return this.set(n*c,n*l,-n*(c*o+l*a)+o+t,-s*l,s*c,-s*(-l*o+c*a)+a+e,0,0,1),this}scale(t,e){return Fe("Matrix3: .scale() is deprecated. Use .makeScale() instead."),this.premultiply(_i.makeScale(t,e)),this}rotate(t){return Fe("Matrix3: .rotate() is deprecated. Use .makeRotation() instead."),this.premultiply(_i.makeRotation(-t)),this}translate(t,e){return Fe("Matrix3: .translate() is deprecated. Use .makeTranslation() instead."),this.premultiply(_i.makeTranslation(t,e)),this}makeTranslation(t,e){return t.isVector2?this.set(1,0,t.x,0,1,t.y,0,0,1):this.set(1,0,t,0,1,e,0,0,1),this}makeRotation(t){let e=Math.cos(t),n=Math.sin(t);return this.set(e,-n,0,n,e,0,0,0,1),this}makeScale(t,e){return this.set(t,0,0,0,e,0,0,0,1),this}equals(t){let e=this.elements,n=t.elements;for(let s=0;s<9;s++)if(e[s]!==n[s])return!1;return!0}fromArray(t,e=0){for(let n=0;n<9;n++)this.elements[n]=t[n+e];return this}toArray(t=[],e=0){let n=this.elements;return t[e]=n[0],t[e+1]=n[1],t[e+2]=n[2],t[e+3]=n[3],t[e+4]=n[4],t[e+5]=n[5],t[e+6]=n[6],t[e+7]=n[7],t[e+8]=n[8],t}clone(){return new this.constructor().fromArray(this.elements)}},_i=new Y,Hs=new Y().set(.4123908,.3575843,.1804808,.212639,.7151687,.0721923,.0193308,.1191948,.9505322),Ws=new Y().set(3.2409699,-1.5373832,-.4986108,-.9692436,1.8759675,.0415551,.0556301,-.203977,1.0569715);function Qo(){let i={enabled:!0,workingColorSpace:ki,spaces:{},convert:p(function(s,r,o){return this.enabled===!1||r===o||!r||!o||(this.spaces[r].transfer===Un&&(s.r=Zt(s.r),s.g=Zt(s.g),s.b=Zt(s.b)),this.spaces[r].primaries!==this.spaces[o].primaries&&(s.applyMatrix3(this.spaces[r].toXYZ),s.applyMatrix3(this.spaces[o].fromXYZ)),this.spaces[o].transfer===Un&&(s.r=Oe(s.r),s.g=Oe(s.g),s.b=Oe(s.b))),s},"convert"),workingToColorSpace:p(function(s,r){return this.convert(s,this.workingColorSpace,r)},"workingToColorSpace"),colorSpaceToWorking:p(function(s,r){return this.convert(s,r,this.workingColorSpace)},"colorSpaceToWorking"),getPrimaries:p(function(s){return this.spaces[s].primaries},"getPrimaries"),getTransfer:p(function(s){return s===os?Vi:this.spaces[s].transfer},"getTransfer"),getToneMappingMode:p(function(s){return this.spaces[s].outputColorSpaceConfig.toneMappingMode||"standard"},"getToneMappingMode"),getLuminanceCoefficients:p(function(s,r=this.workingColorSpace){return s.fromArray(this.spaces[r].luminanceCoefficients)},"getLuminanceCoefficients"),define:p(function(s){Object.assign(this.spaces,s)},"define"),_getMatrix:p(function(s,r,o){return s.copy(this.spaces[r].toXYZ).multiply(this.spaces[o].fromXYZ)},"_getMatrix"),_getDrawingBufferColorSpace:p(function(s){return this.spaces[s].outputColorSpaceConfig.drawingBufferColorSpace},"_getDrawingBufferColorSpace"),_getUnpackColorSpace:p(function(s=this.workingColorSpace){return this.spaces[s].workingColorSpaceConfig.unpackColorSpace},"_getUnpackColorSpace"),fromWorkingColorSpace:p(function(s,r){return Fe("ColorManagement: .fromWorkingColorSpace() has been renamed to .workingToColorSpace()."),i.workingToColorSpace(s,r)},"fromWorkingColorSpace"),toWorkingColorSpace:p(function(s,r){return Fe("ColorManagement: .toWorkingColorSpace() has been renamed to .colorSpaceToWorking()."),i.colorSpaceToWorking(s,r)},"toWorkingColorSpace")},t=[.64,.33,.3,.6,.15,.06],e=[.2126,.7152,.0722],n=[.3127,.329];return i.define({[ki]:{primaries:t,whitePoint:n,transfer:Vi,toXYZ:Hs,fromXYZ:Ws,luminanceCoefficients:e,workingColorSpaceConfig:{unpackColorSpace:Ot},outputColorSpaceConfig:{drawingBufferColorSpace:Ot}},[Ot]:{primaries:t,whitePoint:n,transfer:Un,toXYZ:Hs,fromXYZ:Ws,luminanceCoefficients:e,outputColorSpaceConfig:{drawingBufferColorSpace:Ot}}}),i}p(Qo,"createColorManagement");var Ft=Qo();function Zt(i){return i<.04045?i*.0773993808:Math.pow(i*.9478672986+.0521327014,2.4)}p(Zt,"SRGBToLinear");function Oe(i){return i<.0031308?i*12.92:1.055*Math.pow(i,.41666)-.055}p(Oe,"LinearToSRGB");var Ce,Bn=class{static{p(this,"ImageUtils")}static getDataURL(t,e="image/png"){if(/^data:/i.test(t.src)||typeof HTMLCanvasElement>"u")return t.src;let n;if(t instanceof HTMLCanvasElement)n=t;else{Ce===void 0&&(Ce=Wi("canvas")),Ce.width=t.width,Ce.height=t.height;let s=Ce.getContext("2d");t instanceof ImageData?s.putImageData(t,0,0):s.drawImage(t,0,0,t.width,t.height),n=Ce}return n.toDataURL(e)}static sRGBToLinear(t){if(typeof HTMLImageElement<"u"&&t instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&t instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&t instanceof ImageBitmap){let e=Wi("canvas");e.width=t.width,e.height=t.height;let n=e.getContext("2d");n.drawImage(t,0,0,t.width,t.height);let s=n.getImageData(0,0,t.width,t.height),r=s.data;for(let o=0;o<r.length;o++)r[o]=Zt(r[o]/255)*255;return n.putImageData(s,0,0),e}else if(t.data){let e=t.data.slice(0);for(let n=0;n<e.length;n++)e instanceof Uint8Array||e instanceof Uint8ClampedArray?e[n]=Math.floor(Zt(e[n]/255)*255):e[n]=Zt(e[n]);return{data:e,width:t.width,height:t.height}}else return dt("ImageUtils.sRGBToLinear(): Unsupported image type. No color space conversion applied."),t}},ta=0,zn=class{static{p(this,"Source")}constructor(t=null){this.isSource=!0,Object.defineProperty(this,"id",{value:ta++}),this.uuid=ti(),this.data=t,this.dataReady=!0,this.version=0}getSize(t){let e=this.data;return typeof HTMLVideoElement<"u"&&e instanceof HTMLVideoElement?t.set(e.videoWidth,e.videoHeight,0):typeof VideoFrame<"u"&&e instanceof VideoFrame?t.set(e.displayWidth,e.displayHeight,0):e!==null?t.set(e.width,e.height,e.depth||0):t.set(0,0,0),t}set needsUpdate(t){t===!0&&this.version++}toJSON(t){let e=t===void 0||typeof t=="string";if(!e&&t.images[this.uuid]!==void 0)return t.images[this.uuid];let n={uuid:this.uuid,url:""},s=this.data;if(s!==null){let r;if(Array.isArray(s)){r=[];for(let o=0,a=s.length;o<a;o++)s[o].isDataTexture?r.push(yi(s[o].image)):r.push(yi(s[o]))}else r=yi(s);n.url=r}return e||(t.images[this.uuid]=n),n}};function yi(i){return typeof HTMLImageElement<"u"&&i instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&i instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&i instanceof ImageBitmap?Bn.getDataURL(i):i.data?{data:Array.from(i.data),width:i.width,height:i.height,type:i.data.constructor.name}:(dt("Texture: Unable to serialize Texture."),{})}p(yi,"serializeImage");var ea=0,vi=new k,Be=class i extends me{static{p(this,"Texture")}constructor(t=i.DEFAULT_IMAGE,e=i.DEFAULT_MAPPING,n=rn,s=rn,r=lr,o=hr,a=dr,c=ur,l=i.DEFAULT_ANISOTROPY,h=os){super(),this.isTexture=!0,Object.defineProperty(this,"id",{value:ea++}),this.uuid=ti(),this.name="",this.source=new zn(t),this.mipmaps=[],this.mapping=e,this.channel=0,this.wrapS=n,this.wrapT=s,this.magFilter=r,this.minFilter=o,this.anisotropy=l,this.format=a,this.internalFormat=null,this.type=c,this.offset=new pt(0,0),this.repeat=new pt(1,1),this.center=new pt(0,0),this.rotation=0,this.matrixAutoUpdate=!0,this.matrix=new Y,this.generateMipmaps=!0,this.premultiplyAlpha=!1,this.flipY=!0,this.unpackAlignment=4,this.colorSpace=h,this.userData={},this.updateRanges=[],this.version=0,this.onUpdate=null,this.renderTarget=null,this.isRenderTargetTexture=!1,this.isArrayTexture=!!(t&&t.depth&&t.depth>1),this.pmremVersion=0,this.normalized=!1}get width(){return this.source.getSize(vi).x}get height(){return this.source.getSize(vi).y}get depth(){return this.source.getSize(vi).z}get image(){return this.source.data}set image(t){this.source.data=t}updateMatrix(){this.matrix.setUvTransform(this.offset.x,this.offset.y,this.repeat.x,this.repeat.y,this.rotation,this.center.x,this.center.y)}addUpdateRange(t,e){this.updateRanges.push({start:t,count:e})}clearUpdateRanges(){this.updateRanges.length=0}clone(){return new this.constructor().copy(this)}copy(t){return this.name=t.name,this.source=t.source,this.mipmaps=t.mipmaps.slice(0),this.mapping=t.mapping,this.channel=t.channel,this.wrapS=t.wrapS,this.wrapT=t.wrapT,this.magFilter=t.magFilter,this.minFilter=t.minFilter,this.anisotropy=t.anisotropy,this.format=t.format,this.internalFormat=t.internalFormat,this.type=t.type,this.normalized=t.normalized,this.offset.copy(t.offset),this.repeat.copy(t.repeat),this.center.copy(t.center),this.rotation=t.rotation,this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrix.copy(t.matrix),this.generateMipmaps=t.generateMipmaps,this.premultiplyAlpha=t.premultiplyAlpha,this.flipY=t.flipY,this.unpackAlignment=t.unpackAlignment,this.colorSpace=t.colorSpace,this.renderTarget=t.renderTarget,this.isRenderTargetTexture=t.isRenderTargetTexture,this.isArrayTexture=t.isArrayTexture,this.userData=JSON.parse(JSON.stringify(t.userData)),this.needsUpdate=!0,this}setValues(t){for(let e in t){let n=t[e];if(n===void 0){dt(`Texture.setValues(): parameter '${e}' has value of undefined.`);continue}let s=this[e];if(s===void 0){dt(`Texture.setValues(): property '${e}' does not exist.`);continue}s&&n&&s.isVector2&&n.isVector2||s&&n&&s.isVector3&&n.isVector3||s&&n&&s.isMatrix3&&n.isMatrix3?s.copy(n):this[e]=n}}toJSON(t){let e=t===void 0||typeof t=="string";if(!e&&t.textures[this.uuid]!==void 0)return t.textures[this.uuid];let n={metadata:{version:4.7,type:"Texture",generator:"Texture.toJSON"},uuid:this.uuid,name:this.name,image:this.source.toJSON(t).uuid,mapping:this.mapping,channel:this.channel,repeat:[this.repeat.x,this.repeat.y],offset:[this.offset.x,this.offset.y],center:[this.center.x,this.center.y],rotation:this.rotation,wrap:[this.wrapS,this.wrapT],format:this.format,internalFormat:this.internalFormat,type:this.type,normalized:this.normalized,colorSpace:this.colorSpace,minFilter:this.minFilter,magFilter:this.magFilter,anisotropy:this.anisotropy,flipY:this.flipY,generateMipmaps:this.generateMipmaps,premultiplyAlpha:this.premultiplyAlpha,unpackAlignment:this.unpackAlignment};return Object.keys(this.userData).length>0&&(n.userData=this.userData),e||(t.textures[this.uuid]=n),n}dispose(){this.dispatchEvent({type:"dispose"})}transformUv(t){if(this.mapping!==ss)return t;if(t.applyMatrix3(this.matrix),t.x<0||t.x>1)switch(this.wrapS){case Di:t.x=t.x-Math.floor(t.x);break;case rn:t.x=t.x<0?0:1;break;case Ui:Math.abs(Math.floor(t.x)%2)===1?t.x=Math.ceil(t.x)-t.x:t.x=t.x-Math.floor(t.x);break}if(t.y<0||t.y>1)switch(this.wrapT){case Di:t.y=t.y-Math.floor(t.y);break;case rn:t.y=t.y<0?0:1;break;case Ui:Math.abs(Math.floor(t.y)%2)===1?t.y=Math.ceil(t.y)-t.y:t.y=t.y-Math.floor(t.y);break}return this.flipY&&(t.y=1-t.y),t}set needsUpdate(t){t===!0&&(this.version++,this.source.needsUpdate=!0)}set needsPMREMUpdate(t){t===!0&&this.pmremVersion++}};Be.DEFAULT_IMAGE=null;Be.DEFAULT_MAPPING=ss;Be.DEFAULT_ANISOTROPY=1;var Xi=class i{static{p(this,"Vector4")}static{i.prototype.isVector4=!0}constructor(t=0,e=0,n=0,s=1){this.x=t,this.y=e,this.z=n,this.w=s}get width(){return this.z}set width(t){this.z=t}get height(){return this.w}set height(t){this.w=t}set(t,e,n,s){return this.x=t,this.y=e,this.z=n,this.w=s,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this.w=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setW(t){return this.w=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;case 3:this.w=e;break;default:throw new Error("THREE.Vector4: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;case 3:return this.w;default:throw new Error("THREE.Vector4: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z,this.w)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this.w=t.w!==void 0?t.w:1,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this.w+=t.w,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this.w+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this.w=t.w+e.w,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this.w+=t.w*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this.w-=t.w,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this.w-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this.w=t.w-e.w,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this.w*=t.w,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this.w*=t,this}applyMatrix4(t){let e=this.x,n=this.y,s=this.z,r=this.w,o=t.elements;return this.x=o[0]*e+o[4]*n+o[8]*s+o[12]*r,this.y=o[1]*e+o[5]*n+o[9]*s+o[13]*r,this.z=o[2]*e+o[6]*n+o[10]*s+o[14]*r,this.w=o[3]*e+o[7]*n+o[11]*s+o[15]*r,this}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this.w/=t.w,this}divideScalar(t){return this.multiplyScalar(1/t)}setAxisAngleFromQuaternion(t){this.w=2*Math.acos(t.w);let e=Math.sqrt(1-t.w*t.w);return e<1e-4?(this.x=1,this.y=0,this.z=0):(this.x=t.x/e,this.y=t.y/e,this.z=t.z/e),this}setAxisAngleFromRotationMatrix(t){let e,n,s,r,c=t.elements,l=c[0],h=c[4],u=c[8],f=c[1],d=c[5],m=c[9],g=c[2],_=c[6],x=c[10];if(Math.abs(h-f)<.01&&Math.abs(u-g)<.01&&Math.abs(m-_)<.01){if(Math.abs(h+f)<.1&&Math.abs(u+g)<.1&&Math.abs(m+_)<.1&&Math.abs(l+d+x-3)<.1)return this.set(1,0,0,0),this;e=Math.PI;let y=(l+1)/2,v=(d+1)/2,b=(x+1)/2,A=(h+f)/4,w=(u+g)/4,S=(m+_)/4;return y>v&&y>b?y<.01?(n=0,s=.707106781,r=.707106781):(n=Math.sqrt(y),s=A/n,r=w/n):v>b?v<.01?(n=.707106781,s=0,r=.707106781):(s=Math.sqrt(v),n=A/s,r=S/s):b<.01?(n=.707106781,s=.707106781,r=0):(r=Math.sqrt(b),n=w/r,s=S/r),this.set(n,s,r,e),this}let M=Math.sqrt((_-m)*(_-m)+(u-g)*(u-g)+(f-h)*(f-h));return Math.abs(M)<.001&&(M=1),this.x=(_-m)/M,this.y=(u-g)/M,this.z=(f-h)/M,this.w=Math.acos((l+d+x-1)/2),this}setFromMatrixPosition(t){let e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this.w=e[15],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this.w=Math.min(this.w,t.w),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this.w=Math.max(this.w,t.w),this}clamp(t,e){return this.x=J(this.x,t.x,e.x),this.y=J(this.y,t.y,e.y),this.z=J(this.z,t.z,e.z),this.w=J(this.w,t.w,e.w),this}clampScalar(t,e){return this.x=J(this.x,t,e),this.y=J(this.y,t,e),this.z=J(this.z,t,e),this.w=J(this.w,t,e),this}clampLength(t,e){let n=this.length();return this.divideScalar(n||1).multiplyScalar(J(n,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this.w=Math.floor(this.w),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this.w=Math.ceil(this.w),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this.w=Math.round(this.w),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this.w=Math.trunc(this.w),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this.w=-this.w,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z+this.w*t.w}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)+Math.abs(this.w)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this.w+=(t.w-this.w)*e,this}lerpVectors(t,e,n){return this.x=t.x+(e.x-t.x)*n,this.y=t.y+(e.y-t.y)*n,this.z=t.z+(e.z-t.z)*n,this.w=t.w+(e.w-t.w)*n,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z&&t.w===this.w}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this.w=t[e+3],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t[e+3]=this.w,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this.w=t.getW(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this.w=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z,yield this.w}};var mt=class i{static{p(this,"Matrix4")}static{i.prototype.isMatrix4=!0}constructor(t,e,n,s,r,o,a,c,l,h,u,f,d,m,g,_){this.elements=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],t!==void 0&&this.set(t,e,n,s,r,o,a,c,l,h,u,f,d,m,g,_)}set(t,e,n,s,r,o,a,c,l,h,u,f,d,m,g,_){let x=this.elements;return x[0]=t,x[4]=e,x[8]=n,x[12]=s,x[1]=r,x[5]=o,x[9]=a,x[13]=c,x[2]=l,x[6]=h,x[10]=u,x[14]=f,x[3]=d,x[7]=m,x[11]=g,x[15]=_,this}identity(){return this.set(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),this}clone(){return new i().fromArray(this.elements)}copy(t){let e=this.elements,n=t.elements;return e[0]=n[0],e[1]=n[1],e[2]=n[2],e[3]=n[3],e[4]=n[4],e[5]=n[5],e[6]=n[6],e[7]=n[7],e[8]=n[8],e[9]=n[9],e[10]=n[10],e[11]=n[11],e[12]=n[12],e[13]=n[13],e[14]=n[14],e[15]=n[15],this}copyPosition(t){let e=this.elements,n=t.elements;return e[12]=n[12],e[13]=n[13],e[14]=n[14],this}setFromMatrix3(t){let e=t.elements;return this.set(e[0],e[3],e[6],0,e[1],e[4],e[7],0,e[2],e[5],e[8],0,0,0,0,1),this}extractBasis(t,e,n){return this.determinantAffine()===0?(t.set(1,0,0),e.set(0,1,0),n.set(0,0,1),this):(t.setFromMatrixColumn(this,0),e.setFromMatrixColumn(this,1),n.setFromMatrixColumn(this,2),this)}makeBasis(t,e,n){return this.set(t.x,e.x,n.x,0,t.y,e.y,n.y,0,t.z,e.z,n.z,0,0,0,0,1),this}extractRotation(t){if(t.determinantAffine()===0)return this.identity();let e=this.elements,n=t.elements,s=1/Re.setFromMatrixColumn(t,0).length(),r=1/Re.setFromMatrixColumn(t,1).length(),o=1/Re.setFromMatrixColumn(t,2).length();return e[0]=n[0]*s,e[1]=n[1]*s,e[2]=n[2]*s,e[3]=0,e[4]=n[4]*r,e[5]=n[5]*r,e[6]=n[6]*r,e[7]=0,e[8]=n[8]*o,e[9]=n[9]*o,e[10]=n[10]*o,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromEuler(t){let e=this.elements,n=t.x,s=t.y,r=t.z,o=Math.cos(n),a=Math.sin(n),c=Math.cos(s),l=Math.sin(s),h=Math.cos(r),u=Math.sin(r);if(t.order==="XYZ"){let f=o*h,d=o*u,m=a*h,g=a*u;e[0]=c*h,e[4]=-c*u,e[8]=l,e[1]=d+m*l,e[5]=f-g*l,e[9]=-a*c,e[2]=g-f*l,e[6]=m+d*l,e[10]=o*c}else if(t.order==="YXZ"){let f=c*h,d=c*u,m=l*h,g=l*u;e[0]=f+g*a,e[4]=m*a-d,e[8]=o*l,e[1]=o*u,e[5]=o*h,e[9]=-a,e[2]=d*a-m,e[6]=g+f*a,e[10]=o*c}else if(t.order==="ZXY"){let f=c*h,d=c*u,m=l*h,g=l*u;e[0]=f-g*a,e[4]=-o*u,e[8]=m+d*a,e[1]=d+m*a,e[5]=o*h,e[9]=g-f*a,e[2]=-o*l,e[6]=a,e[10]=o*c}else if(t.order==="ZYX"){let f=o*h,d=o*u,m=a*h,g=a*u;e[0]=c*h,e[4]=m*l-d,e[8]=f*l+g,e[1]=c*u,e[5]=g*l+f,e[9]=d*l-m,e[2]=-l,e[6]=a*c,e[10]=o*c}else if(t.order==="YZX"){let f=o*c,d=o*l,m=a*c,g=a*l;e[0]=c*h,e[4]=g-f*u,e[8]=m*u+d,e[1]=u,e[5]=o*h,e[9]=-a*h,e[2]=-l*h,e[6]=d*u+m,e[10]=f-g*u}else if(t.order==="XZY"){let f=o*c,d=o*l,m=a*c,g=a*l;e[0]=c*h,e[4]=-u,e[8]=l*h,e[1]=f*u+g,e[5]=o*h,e[9]=d*u-m,e[2]=m*u-d,e[6]=a*h,e[10]=g*u+f}return e[3]=0,e[7]=0,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromQuaternion(t){return this.compose(na,t,ia)}lookAt(t,e,n){let s=this.elements;return Ct.subVectors(t,e),Ct.lengthSq()===0&&(Ct.z=1),Ct.normalize(),Qt.crossVectors(n,Ct),Qt.lengthSq()===0&&(Math.abs(n.z)===1?Ct.x+=1e-4:Ct.z+=1e-4,Ct.normalize(),Qt.crossVectors(n,Ct)),Qt.normalize(),An.crossVectors(Ct,Qt),s[0]=Qt.x,s[4]=An.x,s[8]=Ct.x,s[1]=Qt.y,s[5]=An.y,s[9]=Ct.y,s[2]=Qt.z,s[6]=An.z,s[10]=Ct.z,this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){let n=t.elements,s=e.elements,r=this.elements,o=n[0],a=n[4],c=n[8],l=n[12],h=n[1],u=n[5],f=n[9],d=n[13],m=n[2],g=n[6],_=n[10],x=n[14],M=n[3],y=n[7],v=n[11],b=n[15],A=s[0],w=s[4],S=s[8],C=s[12],T=s[1],D=s[5],L=s[9],P=s[13],R=s[2],I=s[6],E=s[10],F=s[14],O=s[3],N=s[7],U=s[11],z=s[15];return r[0]=o*A+a*T+c*R+l*O,r[4]=o*w+a*D+c*I+l*N,r[8]=o*S+a*L+c*E+l*U,r[12]=o*C+a*P+c*F+l*z,r[1]=h*A+u*T+f*R+d*O,r[5]=h*w+u*D+f*I+d*N,r[9]=h*S+u*L+f*E+d*U,r[13]=h*C+u*P+f*F+d*z,r[2]=m*A+g*T+_*R+x*O,r[6]=m*w+g*D+_*I+x*N,r[10]=m*S+g*L+_*E+x*U,r[14]=m*C+g*P+_*F+x*z,r[3]=M*A+y*T+v*R+b*O,r[7]=M*w+y*D+v*I+b*N,r[11]=M*S+y*L+v*E+b*U,r[15]=M*C+y*P+v*F+b*z,this}multiplyScalar(t){let e=this.elements;return e[0]*=t,e[4]*=t,e[8]*=t,e[12]*=t,e[1]*=t,e[5]*=t,e[9]*=t,e[13]*=t,e[2]*=t,e[6]*=t,e[10]*=t,e[14]*=t,e[3]*=t,e[7]*=t,e[11]*=t,e[15]*=t,this}determinant(){let t=this.elements,e=t[0],n=t[4],s=t[8],r=t[12],o=t[1],a=t[5],c=t[9],l=t[13],h=t[2],u=t[6],f=t[10],d=t[14],m=t[3],g=t[7],_=t[11],x=t[15],M=c*d-l*f,y=a*d-l*u,v=a*f-c*u,b=o*d-l*h,A=o*f-c*h,w=o*u-a*h;return e*(g*M-_*y+x*v)-n*(m*M-_*b+x*A)+s*(m*y-g*b+x*w)-r*(m*v-g*A+_*w)}determinantAffine(){let t=this.elements,e=t[0],n=t[4],s=t[8],r=t[1],o=t[5],a=t[9],c=t[2],l=t[6],h=t[10];return e*(o*h-a*l)-n*(r*h-a*c)+s*(r*l-o*c)}transpose(){let t=this.elements,e;return e=t[1],t[1]=t[4],t[4]=e,e=t[2],t[2]=t[8],t[8]=e,e=t[6],t[6]=t[9],t[9]=e,e=t[3],t[3]=t[12],t[12]=e,e=t[7],t[7]=t[13],t[13]=e,e=t[11],t[11]=t[14],t[14]=e,this}setPosition(t,e,n){let s=this.elements;return t.isVector3?(s[12]=t.x,s[13]=t.y,s[14]=t.z):(s[12]=t,s[13]=e,s[14]=n),this}invert(){let t=this.elements,e=t[0],n=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],h=t[8],u=t[9],f=t[10],d=t[11],m=t[12],g=t[13],_=t[14],x=t[15],M=e*a-n*o,y=e*c-s*o,v=e*l-r*o,b=n*c-s*a,A=n*l-r*a,w=s*l-r*c,S=h*g-u*m,C=h*_-f*m,T=h*x-d*m,D=u*_-f*g,L=u*x-d*g,P=f*x-d*_,R=M*P-y*L+v*D+b*T-A*C+w*S;if(R===0)return this.set(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0);let I=1/R;return t[0]=(a*P-c*L+l*D)*I,t[1]=(s*L-n*P-r*D)*I,t[2]=(g*w-_*A+x*b)*I,t[3]=(f*A-u*w-d*b)*I,t[4]=(c*T-o*P-l*C)*I,t[5]=(e*P-s*T+r*C)*I,t[6]=(_*v-m*w-x*y)*I,t[7]=(h*w-f*v+d*y)*I,t[8]=(o*L-a*T+l*S)*I,t[9]=(n*T-e*L-r*S)*I,t[10]=(m*A-g*v+x*M)*I,t[11]=(u*v-h*A-d*M)*I,t[12]=(a*C-o*D-c*S)*I,t[13]=(e*D-n*C+s*S)*I,t[14]=(g*y-m*b-_*M)*I,t[15]=(h*b-u*y+f*M)*I,this}scale(t){let e=this.elements,n=t.x,s=t.y,r=t.z;return e[0]*=n,e[4]*=s,e[8]*=r,e[1]*=n,e[5]*=s,e[9]*=r,e[2]*=n,e[6]*=s,e[10]*=r,e[3]*=n,e[7]*=s,e[11]*=r,this}getMaxScaleOnAxis(){let t=this.elements,e=t[0]*t[0]+t[1]*t[1]+t[2]*t[2],n=t[4]*t[4]+t[5]*t[5]+t[6]*t[6],s=t[8]*t[8]+t[9]*t[9]+t[10]*t[10];return Math.sqrt(Math.max(e,n,s))}makeTranslation(t,e,n){return t.isVector3?this.set(1,0,0,t.x,0,1,0,t.y,0,0,1,t.z,0,0,0,1):this.set(1,0,0,t,0,1,0,e,0,0,1,n,0,0,0,1),this}makeRotationX(t){let e=Math.cos(t),n=Math.sin(t);return this.set(1,0,0,0,0,e,-n,0,0,n,e,0,0,0,0,1),this}makeRotationY(t){let e=Math.cos(t),n=Math.sin(t);return this.set(e,0,n,0,0,1,0,0,-n,0,e,0,0,0,0,1),this}makeRotationZ(t){let e=Math.cos(t),n=Math.sin(t);return this.set(e,-n,0,0,n,e,0,0,0,0,1,0,0,0,0,1),this}makeRotationAxis(t,e){let n=Math.cos(e),s=Math.sin(e),r=1-n,o=t.x,a=t.y,c=t.z,l=r*o,h=r*a;return this.set(l*o+n,l*a-s*c,l*c+s*a,0,l*a+s*c,h*a+n,h*c-s*o,0,l*c-s*a,h*c+s*o,r*c*c+n,0,0,0,0,1),this}makeScale(t,e,n){return this.set(t,0,0,0,0,e,0,0,0,0,n,0,0,0,0,1),this}makeShear(t,e,n,s,r,o){return this.set(1,n,r,0,t,1,o,0,e,s,1,0,0,0,0,1),this}compose(t,e,n){let s=this.elements,r=e._x,o=e._y,a=e._z,c=e._w,l=r+r,h=o+o,u=a+a,f=r*l,d=r*h,m=r*u,g=o*h,_=o*u,x=a*u,M=c*l,y=c*h,v=c*u,b=n.x,A=n.y,w=n.z;return s[0]=(1-(g+x))*b,s[1]=(d+v)*b,s[2]=(m-y)*b,s[3]=0,s[4]=(d-v)*A,s[5]=(1-(f+x))*A,s[6]=(_+M)*A,s[7]=0,s[8]=(m+y)*w,s[9]=(_-M)*w,s[10]=(1-(f+g))*w,s[11]=0,s[12]=t.x,s[13]=t.y,s[14]=t.z,s[15]=1,this}decompose(t,e,n){let s=this.elements;t.x=s[12],t.y=s[13],t.z=s[14];let r=this.determinantAffine();if(r===0)return n.set(1,1,1),e.identity(),this;let o=Re.set(s[0],s[1],s[2]).length(),a=Re.set(s[4],s[5],s[6]).length(),c=Re.set(s[8],s[9],s[10]).length();r<0&&(o=-o),Vt.copy(this);let l=1/o,h=1/a,u=1/c;return Vt.elements[0]*=l,Vt.elements[1]*=l,Vt.elements[2]*=l,Vt.elements[4]*=h,Vt.elements[5]*=h,Vt.elements[6]*=h,Vt.elements[8]*=u,Vt.elements[9]*=u,Vt.elements[10]*=u,e.setFromRotationMatrix(Vt),n.x=o,n.y=a,n.z=c,this}makePerspective(t,e,n,s,r,o,a=on,c=!1){let l=this.elements,h=2*r/(e-t),u=2*r/(n-s),f=(e+t)/(e-t),d=(n+s)/(n-s),m,g;if(c)m=r/(o-r),g=o*r/(o-r);else if(a===on)m=-(o+r)/(o-r),g=-2*o*r/(o-r);else if(a===Hi)m=-o/(o-r),g=-o*r/(o-r);else throw new Error("THREE.Matrix4.makePerspective(): Invalid coordinate system: "+a);return l[0]=h,l[4]=0,l[8]=f,l[12]=0,l[1]=0,l[5]=u,l[9]=d,l[13]=0,l[2]=0,l[6]=0,l[10]=m,l[14]=g,l[3]=0,l[7]=0,l[11]=-1,l[15]=0,this}makeOrthographic(t,e,n,s,r,o,a=on,c=!1){let l=this.elements,h=2/(e-t),u=2/(n-s),f=-(e+t)/(e-t),d=-(n+s)/(n-s),m,g;if(c)m=1/(o-r),g=o/(o-r);else if(a===on)m=-2/(o-r),g=-(o+r)/(o-r);else if(a===Hi)m=-1/(o-r),g=-r/(o-r);else throw new Error("THREE.Matrix4.makeOrthographic(): Invalid coordinate system: "+a);return l[0]=h,l[4]=0,l[8]=0,l[12]=f,l[1]=0,l[5]=u,l[9]=0,l[13]=d,l[2]=0,l[6]=0,l[10]=m,l[14]=g,l[3]=0,l[7]=0,l[11]=0,l[15]=1,this}equals(t){let e=this.elements,n=t.elements;for(let s=0;s<16;s++)if(e[s]!==n[s])return!1;return!0}fromArray(t,e=0){for(let n=0;n<16;n++)this.elements[n]=t[n+e];return this}toArray(t=[],e=0){let n=this.elements;return t[e]=n[0],t[e+1]=n[1],t[e+2]=n[2],t[e+3]=n[3],t[e+4]=n[4],t[e+5]=n[5],t[e+6]=n[6],t[e+7]=n[7],t[e+8]=n[8],t[e+9]=n[9],t[e+10]=n[10],t[e+11]=n[11],t[e+12]=n[12],t[e+13]=n[13],t[e+14]=n[14],t[e+15]=n[15],t}},Re=new k,Vt=new mt,na=new k(0,0,0),ia=new k(1,1,1),Qt=new k,An=new k,Ct=new k,Xs=new mt,qs=new Ht,ln=class i{static{p(this,"Euler")}constructor(t=0,e=0,n=0,s=i.DEFAULT_ORDER){this.isEuler=!0,this._x=t,this._y=e,this._z=n,this._order=s}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get order(){return this._order}set order(t){this._order=t,this._onChangeCallback()}set(t,e,n,s=this._order){return this._x=t,this._y=e,this._z=n,this._order=s,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._order)}copy(t){return this._x=t._x,this._y=t._y,this._z=t._z,this._order=t._order,this._onChangeCallback(),this}setFromRotationMatrix(t,e=this._order,n=!0){let s=t.elements,r=s[0],o=s[4],a=s[8],c=s[1],l=s[5],h=s[9],u=s[2],f=s[6],d=s[10];switch(e){case"XYZ":this._y=Math.asin(J(a,-1,1)),Math.abs(a)<.9999999?(this._x=Math.atan2(-h,d),this._z=Math.atan2(-o,r)):(this._x=Math.atan2(f,l),this._z=0);break;case"YXZ":this._x=Math.asin(-J(h,-1,1)),Math.abs(h)<.9999999?(this._y=Math.atan2(a,d),this._z=Math.atan2(c,l)):(this._y=Math.atan2(-u,r),this._z=0);break;case"ZXY":this._x=Math.asin(J(f,-1,1)),Math.abs(f)<.9999999?(this._y=Math.atan2(-u,d),this._z=Math.atan2(-o,l)):(this._y=0,this._z=Math.atan2(c,r));break;case"ZYX":this._y=Math.asin(-J(u,-1,1)),Math.abs(u)<.9999999?(this._x=Math.atan2(f,d),this._z=Math.atan2(c,r)):(this._x=0,this._z=Math.atan2(-o,l));break;case"YZX":this._z=Math.asin(J(c,-1,1)),Math.abs(c)<.9999999?(this._x=Math.atan2(-h,l),this._y=Math.atan2(-u,r)):(this._x=0,this._y=Math.atan2(a,d));break;case"XZY":this._z=Math.asin(-J(o,-1,1)),Math.abs(o)<.9999999?(this._x=Math.atan2(f,l),this._y=Math.atan2(a,r)):(this._x=Math.atan2(-h,d),this._y=0);break;default:dt("Euler: .setFromRotationMatrix() encountered an unknown order: "+e)}return this._order=e,n===!0&&this._onChangeCallback(),this}setFromQuaternion(t,e,n){return Xs.makeRotationFromQuaternion(t),this.setFromRotationMatrix(Xs,e,n)}setFromVector3(t,e=this._order){return this.set(t.x,t.y,t.z,e)}reorder(t){return qs.setFromEuler(this),this.setFromQuaternion(qs,t)}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._order===this._order}fromArray(t){return this._x=t[0],this._y=t[1],this._z=t[2],t[3]!==void 0&&(this._order=t[3]),this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._order,t}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._order}};ln.DEFAULT_ORDER="XYZ";var kn=class{static{p(this,"Layers")}constructor(){this.mask=1}set(t){this.mask=(1<<t|0)>>>0}enable(t){this.mask|=1<<t|0}enableAll(){this.mask=-1}toggle(t){this.mask^=1<<t|0}disable(t){this.mask&=~(1<<t|0)}disableAll(){this.mask=0}test(t){return(this.mask&t.mask)!==0}isEnabled(t){return(this.mask&(1<<t|0))!==0}},sa=0,$s=new k,Ie=new Ht,$t=new mt,wn=new k,tn=new k,ra=new k,oa=new Ht,Ys=new k(1,0,0),Zs=new k(0,1,0),Js=new k(0,0,1),Ks={type:"added"},aa={type:"removed"},Pe={type:"childadded",child:null},Mi={type:"childremoved",child:null},ge=class i extends me{static{p(this,"Object3D")}constructor(){super(),this.isObject3D=!0,Object.defineProperty(this,"id",{value:sa++}),this.uuid=ti(),this.name="",this.type="Object3D",this.parent=null,this.children=[],this.up=i.DEFAULT_UP.clone();let t=new k,e=new ln,n=new Ht,s=new k(1,1,1);function r(){n.setFromEuler(e,!1)}p(r,"onRotationChange");function o(){e.setFromQuaternion(n,void 0,!1)}p(o,"onQuaternionChange"),e._onChange(r),n._onChange(o),Object.defineProperties(this,{position:{configurable:!0,enumerable:!0,value:t},rotation:{configurable:!0,enumerable:!0,value:e},quaternion:{configurable:!0,enumerable:!0,value:n},scale:{configurable:!0,enumerable:!0,value:s},modelViewMatrix:{value:new mt},normalMatrix:{value:new Y}}),this.matrix=new mt,this.matrixWorld=new mt,this.matrixAutoUpdate=i.DEFAULT_MATRIX_AUTO_UPDATE,this.matrixWorldAutoUpdate=i.DEFAULT_MATRIX_WORLD_AUTO_UPDATE,this.matrixWorldNeedsUpdate=!1,this.layers=new kn,this.visible=!0,this.castShadow=!1,this.receiveShadow=!1,this.frustumCulled=!0,this.renderOrder=0,this.animations=[],this.customDepthMaterial=void 0,this.customDistanceMaterial=void 0,this.static=!1,this.userData={},this.pivot=null}onBeforeShadow(){}onAfterShadow(){}onBeforeRender(){}onAfterRender(){}applyMatrix4(t){this.matrixAutoUpdate&&this.updateMatrix(),this.matrix.premultiply(t),this.matrix.decompose(this.position,this.quaternion,this.scale)}applyQuaternion(t){return this.quaternion.premultiply(t),this}setRotationFromAxisAngle(t,e){this.quaternion.setFromAxisAngle(t,e)}setRotationFromEuler(t){this.quaternion.setFromEuler(t,!0)}setRotationFromMatrix(t){this.quaternion.setFromRotationMatrix(t)}setRotationFromQuaternion(t){this.quaternion.copy(t)}rotateOnAxis(t,e){return Ie.setFromAxisAngle(t,e),this.quaternion.multiply(Ie),this}rotateOnWorldAxis(t,e){return Ie.setFromAxisAngle(t,e),this.quaternion.premultiply(Ie),this}rotateX(t){return this.rotateOnAxis(Ys,t)}rotateY(t){return this.rotateOnAxis(Zs,t)}rotateZ(t){return this.rotateOnAxis(Js,t)}translateOnAxis(t,e){return $s.copy(t).applyQuaternion(this.quaternion),this.position.add($s.multiplyScalar(e)),this}translateX(t){return this.translateOnAxis(Ys,t)}translateY(t){return this.translateOnAxis(Zs,t)}translateZ(t){return this.translateOnAxis(Js,t)}localToWorld(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(this.matrixWorld)}worldToLocal(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4($t.copy(this.matrixWorld).invert())}lookAt(t,e,n){t.isVector3?wn.copy(t):wn.set(t,e,n);let s=this.parent;this.updateWorldMatrix(!0,!1),tn.setFromMatrixPosition(this.matrixWorld),this.isCamera||this.isLight?$t.lookAt(tn,wn,this.up):$t.lookAt(wn,tn,this.up),this.quaternion.setFromRotationMatrix($t),s&&($t.extractRotation(s.matrixWorld),Ie.setFromRotationMatrix($t),this.quaternion.premultiply(Ie.invert()))}add(t){if(arguments.length>1){for(let e=0;e<arguments.length;e++)this.add(arguments[e]);return this}return t===this?(st("Object3D.add: object can't be added as a child of itself.",t),this):(t&&t.isObject3D?(t.removeFromParent(),t.parent=this,this.children.push(t),t.dispatchEvent(Ks),Pe.child=t,this.dispatchEvent(Pe),Pe.child=null):st("Object3D.add: object not an instance of THREE.Object3D.",t),this)}remove(t){if(arguments.length>1){for(let n=0;n<arguments.length;n++)this.remove(arguments[n]);return this}let e=this.children.indexOf(t);return e!==-1&&(t.parent=null,this.children.splice(e,1),t.dispatchEvent(aa),Mi.child=t,this.dispatchEvent(Mi),Mi.child=null),this}removeFromParent(){let t=this.parent;return t!==null&&t.remove(this),this}clear(){return this.remove(...this.children)}attach(t){return this.updateWorldMatrix(!0,!1),$t.copy(this.matrixWorld).invert(),t.parent!==null&&(t.parent.updateWorldMatrix(!0,!1),$t.multiply(t.parent.matrixWorld)),t.applyMatrix4($t),t.removeFromParent(),t.parent=this,this.children.push(t),t.updateWorldMatrix(!1,!0),t.dispatchEvent(Ks),Pe.child=t,this.dispatchEvent(Pe),Pe.child=null,this}getObjectById(t){return this.getObjectByProperty("id",t)}getObjectByName(t){return this.getObjectByProperty("name",t)}getObjectByProperty(t,e){if(this[t]===e)return this;for(let n=0,s=this.children.length;n<s;n++){let o=this.children[n].getObjectByProperty(t,e);if(o!==void 0)return o}}getObjectsByProperty(t,e,n=[]){this[t]===e&&n.push(this);let s=this.children;for(let r=0,o=s.length;r<o;r++)s[r].getObjectsByProperty(t,e,n);return n}getWorldPosition(t){return this.updateWorldMatrix(!0,!1),t.setFromMatrixPosition(this.matrixWorld)}getWorldQuaternion(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(tn,t,ra),t}getWorldScale(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(tn,oa,t),t}getWorldDirection(t){this.updateWorldMatrix(!0,!1);let e=this.matrixWorld.elements;return t.set(e[8],e[9],e[10]).normalize()}raycast(){}traverse(t){t(this);let e=this.children;for(let n=0,s=e.length;n<s;n++)e[n].traverse(t)}traverseVisible(t){if(this.visible===!1)return;t(this);let e=this.children;for(let n=0,s=e.length;n<s;n++)e[n].traverseVisible(t)}traverseAncestors(t){let e=this.parent;e!==null&&(t(e),e.traverseAncestors(t))}updateMatrix(){this.matrix.compose(this.position,this.quaternion,this.scale);let t=this.pivot;if(t!==null){let e=t.x,n=t.y,s=t.z,r=this.matrix.elements;r[12]+=e-r[0]*e-r[4]*n-r[8]*s,r[13]+=n-r[1]*e-r[5]*n-r[9]*s,r[14]+=s-r[2]*e-r[6]*n-r[10]*s}this.matrixWorldNeedsUpdate=!0}updateMatrixWorld(t){this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||t)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,t=!0);let e=this.children;for(let n=0,s=e.length;n<s;n++)e[n].updateMatrixWorld(t)}updateWorldMatrix(t,e,n=!1){let s=this.parent;if(t===!0&&s!==null&&s.updateWorldMatrix(!0,!1),this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||n)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,n=!0),e===!0){let r=this.children;for(let o=0,a=r.length;o<a;o++)r[o].updateWorldMatrix(!1,!0,n)}}toJSON(t){let e=t===void 0||typeof t=="string",n={};e&&(t={geometries:{},materials:{},textures:{},images:{},shapes:{},skeletons:{},animations:{},nodes:{}},n.metadata={version:4.7,type:"Object",generator:"Object3D.toJSON"});let s={};s.uuid=this.uuid,s.type=this.type,this.name!==""&&(s.name=this.name),this.castShadow===!0&&(s.castShadow=!0),this.receiveShadow===!0&&(s.receiveShadow=!0),this.visible===!1&&(s.visible=!1),this.frustumCulled===!1&&(s.frustumCulled=!1),this.renderOrder!==0&&(s.renderOrder=this.renderOrder),this.static!==!1&&(s.static=this.static),Object.keys(this.userData).length>0&&(s.userData=this.userData),s.layers=this.layers.mask,s.matrix=this.matrix.toArray(),s.up=this.up.toArray(),this.pivot!==null&&(s.pivot=this.pivot.toArray()),this.matrixAutoUpdate===!1&&(s.matrixAutoUpdate=!1),this.morphTargetDictionary!==void 0&&(s.morphTargetDictionary=Object.assign({},this.morphTargetDictionary)),this.morphTargetInfluences!==void 0&&(s.morphTargetInfluences=this.morphTargetInfluences.slice()),this.isInstancedMesh&&(s.type="InstancedMesh",s.count=this.count,s.instanceMatrix=this.instanceMatrix.toJSON(),this.instanceColor!==null&&(s.instanceColor=this.instanceColor.toJSON())),this.isBatchedMesh&&(s.type="BatchedMesh",s.perObjectFrustumCulled=this.perObjectFrustumCulled,s.sortObjects=this.sortObjects,s.drawRanges=this._drawRanges,s.reservedRanges=this._reservedRanges,s.geometryInfo=this._geometryInfo.map(a=>({...a,boundingBox:a.boundingBox?a.boundingBox.toJSON():void 0,boundingSphere:a.boundingSphere?a.boundingSphere.toJSON():void 0})),s.instanceInfo=this._instanceInfo.map(a=>({...a})),s.availableInstanceIds=this._availableInstanceIds.slice(),s.availableGeometryIds=this._availableGeometryIds.slice(),s.nextIndexStart=this._nextIndexStart,s.nextVertexStart=this._nextVertexStart,s.geometryCount=this._geometryCount,s.maxInstanceCount=this._maxInstanceCount,s.maxVertexCount=this._maxVertexCount,s.maxIndexCount=this._maxIndexCount,s.geometryInitialized=this._geometryInitialized,s.matricesTexture=this._matricesTexture.toJSON(t),s.indirectTexture=this._indirectTexture.toJSON(t),this._colorsTexture!==null&&(s.colorsTexture=this._colorsTexture.toJSON(t)),this.boundingSphere!==null&&(s.boundingSphere=this.boundingSphere.toJSON()),this.boundingBox!==null&&(s.boundingBox=this.boundingBox.toJSON()));function r(a,c){return a[c.uuid]===void 0&&(a[c.uuid]=c.toJSON(t)),c.uuid}if(p(r,"serialize"),this.isScene)this.background&&(this.background.isColor?s.background=this.background.toJSON():this.background.isTexture&&(s.background=this.background.toJSON(t).uuid)),this.environment&&this.environment.isTexture&&this.environment.isRenderTargetTexture!==!0&&(s.environment=this.environment.toJSON(t).uuid);else if(this.isMesh||this.isLine||this.isPoints){s.geometry=r(t.geometries,this.geometry);let a=this.geometry.parameters;if(a!==void 0&&a.shapes!==void 0){let c=a.shapes;if(Array.isArray(c))for(let l=0,h=c.length;l<h;l++){let u=c[l];r(t.shapes,u)}else r(t.shapes,c)}}if(this.isSkinnedMesh&&(s.bindMode=this.bindMode,s.bindMatrix=this.bindMatrix.toArray(),this.skeleton!==void 0&&(r(t.skeletons,this.skeleton),s.skeleton=this.skeleton.uuid)),this.material!==void 0)if(Array.isArray(this.material)){let a=[];for(let c=0,l=this.material.length;c<l;c++)a.push(r(t.materials,this.material[c]));s.material=a}else s.material=r(t.materials,this.material);if(this.children.length>0){s.children=[];for(let a=0;a<this.children.length;a++)s.children.push(this.children[a].toJSON(t).object)}if(this.animations.length>0){s.animations=[];for(let a=0;a<this.animations.length;a++){let c=this.animations[a];s.animations.push(r(t.animations,c))}}if(e){let a=o(t.geometries),c=o(t.materials),l=o(t.textures),h=o(t.images),u=o(t.shapes),f=o(t.skeletons),d=o(t.animations),m=o(t.nodes);a.length>0&&(n.geometries=a),c.length>0&&(n.materials=c),l.length>0&&(n.textures=l),h.length>0&&(n.images=h),u.length>0&&(n.shapes=u),f.length>0&&(n.skeletons=f),d.length>0&&(n.animations=d),m.length>0&&(n.nodes=m)}return n.object=s,n;function o(a){let c=[];for(let l in a){let h=a[l];delete h.metadata,c.push(h)}return c}p(o,"extractFromCache")}clone(t){return new this.constructor().copy(this,t)}copy(t,e=!0){if(this.name=t.name,this.up.copy(t.up),this.position.copy(t.position),this.rotation.order=t.rotation.order,this.quaternion.copy(t.quaternion),this.scale.copy(t.scale),this.pivot=t.pivot!==null?t.pivot.clone():null,this.matrix.copy(t.matrix),this.matrixWorld.copy(t.matrixWorld),this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrixWorldAutoUpdate=t.matrixWorldAutoUpdate,this.matrixWorldNeedsUpdate=t.matrixWorldNeedsUpdate,this.layers.mask=t.layers.mask,this.visible=t.visible,this.castShadow=t.castShadow,this.receiveShadow=t.receiveShadow,this.frustumCulled=t.frustumCulled,this.renderOrder=t.renderOrder,this.static=t.static,this.animations=t.animations.slice(),this.userData=JSON.parse(JSON.stringify(t.userData)),e===!0)for(let n=0;n<t.children.length;n++){let s=t.children[n];this.add(s.clone())}return this}};ge.DEFAULT_UP=new k(0,1,0);ge.DEFAULT_MATRIX_AUTO_UPDATE=!0;ge.DEFAULT_MATRIX_WORLD_AUTO_UPDATE=!0;var mr={aliceblue:15792383,antiquewhite:16444375,aqua:65535,aquamarine:8388564,azure:15794175,beige:16119260,bisque:16770244,black:0,blanchedalmond:16772045,blue:255,blueviolet:9055202,brown:10824234,burlywood:14596231,cadetblue:6266528,chartreuse:8388352,chocolate:13789470,coral:16744272,cornflowerblue:6591981,cornsilk:16775388,crimson:14423100,cyan:65535,darkblue:139,darkcyan:35723,darkgoldenrod:12092939,darkgray:11119017,darkgreen:25600,darkgrey:11119017,darkkhaki:12433259,darkmagenta:9109643,darkolivegreen:5597999,darkorange:16747520,darkorchid:10040012,darkred:9109504,darksalmon:15308410,darkseagreen:9419919,darkslateblue:4734347,darkslategray:3100495,darkslategrey:3100495,darkturquoise:52945,darkviolet:9699539,deeppink:16716947,deepskyblue:49151,dimgray:6908265,dimgrey:6908265,dodgerblue:2003199,firebrick:11674146,floralwhite:16775920,forestgreen:2263842,fuchsia:16711935,gainsboro:14474460,ghostwhite:16316671,gold:16766720,goldenrod:14329120,gray:8421504,green:32768,greenyellow:11403055,grey:8421504,honeydew:15794160,hotpink:16738740,indianred:13458524,indigo:4915330,ivory:16777200,khaki:15787660,lavender:15132410,lavenderblush:16773365,lawngreen:8190976,lemonchiffon:16775885,lightblue:11393254,lightcoral:15761536,lightcyan:14745599,lightgoldenrodyellow:16448210,lightgray:13882323,lightgreen:9498256,lightgrey:13882323,lightpink:16758465,lightsalmon:16752762,lightseagreen:2142890,lightskyblue:8900346,lightslategray:7833753,lightslategrey:7833753,lightsteelblue:11584734,lightyellow:16777184,lime:65280,limegreen:3329330,linen:16445670,magenta:16711935,maroon:8388608,mediumaquamarine:6737322,mediumblue:205,mediumorchid:12211667,mediumpurple:9662683,mediumseagreen:3978097,mediumslateblue:8087790,mediumspringgreen:64154,mediumturquoise:4772300,mediumvioletred:13047173,midnightblue:1644912,mintcream:16121850,mistyrose:16770273,moccasin:16770229,navajowhite:16768685,navy:128,oldlace:16643558,olive:8421376,olivedrab:7048739,orange:16753920,orangered:16729344,orchid:14315734,palegoldenrod:15657130,palegreen:10025880,paleturquoise:11529966,palevioletred:14381203,papayawhip:16773077,peachpuff:16767673,peru:13468991,pink:16761035,plum:14524637,powderblue:11591910,purple:8388736,rebeccapurple:6697881,red:16711680,rosybrown:12357519,royalblue:4286945,saddlebrown:9127187,salmon:16416882,sandybrown:16032864,seagreen:3050327,seashell:16774638,sienna:10506797,silver:12632256,skyblue:8900331,slateblue:6970061,slategray:7372944,slategrey:7372944,snow:16775930,springgreen:65407,steelblue:4620980,tan:13808780,teal:32896,thistle:14204888,tomato:16737095,turquoise:4251856,violet:15631086,wheat:16113331,white:16777215,whitesmoke:16119285,yellow:16776960,yellowgreen:10145074},te={h:0,s:0,l:0},Tn={h:0,s:0,l:0};function Si(i,t,e){return e<0&&(e+=1),e>1&&(e-=1),e<1/6?i+(t-i)*6*e:e<1/2?t:e<2/3?i+(t-i)*6*(2/3-e):i}p(Si,"hue2rgb");var gt=class{static{p(this,"Color")}constructor(t,e,n){return this.isColor=!0,this.r=1,this.g=1,this.b=1,this.set(t,e,n)}set(t,e,n){if(e===void 0&&n===void 0){let s=t;s&&s.isColor?this.copy(s):typeof s=="number"?this.setHex(s):typeof s=="string"&&this.setStyle(s)}else this.setRGB(t,e,n);return this}setScalar(t){return this.r=t,this.g=t,this.b=t,this}setHex(t,e=Ot){return t=Math.floor(t),this.r=(t>>16&255)/255,this.g=(t>>8&255)/255,this.b=(t&255)/255,Ft.colorSpaceToWorking(this,e),this}setRGB(t,e,n,s=Ft.workingColorSpace){return this.r=t,this.g=e,this.b=n,Ft.colorSpaceToWorking(this,s),this}setHSL(t,e,n,s=Ft.workingColorSpace){if(t=jo(t,1),e=J(e,0,1),n=J(n,0,1),e===0)this.r=this.g=this.b=n;else{let r=n<=.5?n*(1+e):n+e-n*e,o=2*n-r;this.r=Si(o,r,t+1/3),this.g=Si(o,r,t),this.b=Si(o,r,t-1/3)}return Ft.colorSpaceToWorking(this,s),this}setStyle(t,e=Ot){function n(r){r!==void 0&&parseFloat(r)<1&&dt("Color: Alpha component of "+t+" will be ignored.")}p(n,"handleAlpha");let s;if(s=/^(\w+)\(([^\)]*)\)/.exec(t)){let r,o=s[1],a=s[2];switch(o){case"rgb":case"rgba":if(r=/^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return n(r[4]),this.setRGB(Math.min(255,parseInt(r[1],10))/255,Math.min(255,parseInt(r[2],10))/255,Math.min(255,parseInt(r[3],10))/255,e);if(r=/^\s*(\d+)\%\s*,\s*(\d+)\%\s*,\s*(\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return n(r[4]),this.setRGB(Math.min(100,parseInt(r[1],10))/100,Math.min(100,parseInt(r[2],10))/100,Math.min(100,parseInt(r[3],10))/100,e);break;case"hsl":case"hsla":if(r=/^\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\%\s*,\s*(\d*\.?\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return n(r[4]),this.setHSL(parseFloat(r[1])/360,parseFloat(r[2])/100,parseFloat(r[3])/100,e);break;default:dt("Color: Unknown color model "+t)}}else if(s=/^\#([A-Fa-f\d]+)$/.exec(t)){let r=s[1],o=r.length;if(o===3)return this.setRGB(parseInt(r.charAt(0),16)/15,parseInt(r.charAt(1),16)/15,parseInt(r.charAt(2),16)/15,e);if(o===6)return this.setHex(parseInt(r,16),e);dt("Color: Invalid hex color "+t)}else if(t&&t.length>0)return this.setColorName(t,e);return this}setColorName(t,e=Ot){let n=mr[t.toLowerCase()];return n!==void 0?this.setHex(n,e):dt("Color: Unknown color "+t),this}clone(){return new this.constructor(this.r,this.g,this.b)}copy(t){return this.r=t.r,this.g=t.g,this.b=t.b,this}copySRGBToLinear(t){return this.r=Zt(t.r),this.g=Zt(t.g),this.b=Zt(t.b),this}copyLinearToSRGB(t){return this.r=Oe(t.r),this.g=Oe(t.g),this.b=Oe(t.b),this}convertSRGBToLinear(){return this.copySRGBToLinear(this),this}convertLinearToSRGB(){return this.copyLinearToSRGB(this),this}getHex(t=Ot){return Ft.workingToColorSpace(Mt.copy(this),t),Math.round(J(Mt.r*255,0,255))*65536+Math.round(J(Mt.g*255,0,255))*256+Math.round(J(Mt.b*255,0,255))}getHexString(t=Ot){return("000000"+this.getHex(t).toString(16)).slice(-6)}getHSL(t,e=Ft.workingColorSpace){Ft.workingToColorSpace(Mt.copy(this),e);let n=Mt.r,s=Mt.g,r=Mt.b,o=Math.max(n,s,r),a=Math.min(n,s,r),c,l,h=(a+o)/2;if(a===o)c=0,l=0;else{let u=o-a;switch(l=h<=.5?u/(o+a):u/(2-o-a),o){case n:c=(s-r)/u+(s<r?6:0);break;case s:c=(r-n)/u+2;break;case r:c=(n-s)/u+4;break}c/=6}return t.h=c,t.s=l,t.l=h,t}getRGB(t,e=Ft.workingColorSpace){return Ft.workingToColorSpace(Mt.copy(this),e),t.r=Mt.r,t.g=Mt.g,t.b=Mt.b,t}getStyle(t=Ot){Ft.workingToColorSpace(Mt.copy(this),t);let e=Mt.r,n=Mt.g,s=Mt.b;return t!==Ot?`color(${t} ${e.toFixed(3)} ${n.toFixed(3)} ${s.toFixed(3)})`:`rgb(${Math.round(e*255)},${Math.round(n*255)},${Math.round(s*255)})`}offsetHSL(t,e,n){return this.getHSL(te),this.setHSL(te.h+t,te.s+e,te.l+n)}add(t){return this.r+=t.r,this.g+=t.g,this.b+=t.b,this}addColors(t,e){return this.r=t.r+e.r,this.g=t.g+e.g,this.b=t.b+e.b,this}addScalar(t){return this.r+=t,this.g+=t,this.b+=t,this}sub(t){return this.r=Math.max(0,this.r-t.r),this.g=Math.max(0,this.g-t.g),this.b=Math.max(0,this.b-t.b),this}multiply(t){return this.r*=t.r,this.g*=t.g,this.b*=t.b,this}multiplyScalar(t){return this.r*=t,this.g*=t,this.b*=t,this}lerp(t,e){return this.r+=(t.r-this.r)*e,this.g+=(t.g-this.g)*e,this.b+=(t.b-this.b)*e,this}lerpColors(t,e,n){return this.r=t.r+(e.r-t.r)*n,this.g=t.g+(e.g-t.g)*n,this.b=t.b+(e.b-t.b)*n,this}lerpHSL(t,e){this.getHSL(te),t.getHSL(Tn);let n=gi(te.h,Tn.h,e),s=gi(te.s,Tn.s,e),r=gi(te.l,Tn.l,e);return this.setHSL(n,s,r),this}setFromVector3(t){return this.r=t.x,this.g=t.y,this.b=t.z,this}applyMatrix3(t){let e=this.r,n=this.g,s=this.b,r=t.elements;return this.r=r[0]*e+r[3]*n+r[6]*s,this.g=r[1]*e+r[4]*n+r[7]*s,this.b=r[2]*e+r[5]*n+r[8]*s,this}equals(t){return t.r===this.r&&t.g===this.g&&t.b===this.b}fromArray(t,e=0){return this.r=t[e],this.g=t[e+1],this.b=t[e+2],this}toArray(t=[],e=0){return t[e]=this.r,t[e+1]=this.g,t[e+2]=this.b,t}fromBufferAttribute(t,e){return this.r=t.getX(e),this.g=t.getY(e),this.b=t.getZ(e),this}toJSON(){return this.getHex()}*[Symbol.iterator](){yield this.r,yield this.g,yield this.b}},Mt=new gt;gt.NAMES=mr;var ie=class{static{p(this,"Box3")}constructor(t=new k(1/0,1/0,1/0),e=new k(-1/0,-1/0,-1/0)){this.isBox3=!0,this.min=t,this.max=e}set(t,e){return this.min.copy(t),this.max.copy(e),this}setFromArray(t){this.makeEmpty();for(let e=0,n=t.length;e<n;e+=3)this.expandByPoint(Gt.fromArray(t,e));return this}setFromBufferAttribute(t){this.makeEmpty();for(let e=0,n=t.count;e<n;e++)this.expandByPoint(Gt.fromBufferAttribute(t,e));return this}setFromPoints(t){this.makeEmpty();for(let e=0,n=t.length;e<n;e++)this.expandByPoint(t[e]);return this}setFromCenterAndSize(t,e){let n=Gt.copy(e).multiplyScalar(.5);return this.min.copy(t).sub(n),this.max.copy(t).add(n),this}setFromObject(t,e=!1){return this.makeEmpty(),this.expandByObject(t,e)}clone(){return new this.constructor().copy(this)}copy(t){return this.min.copy(t.min),this.max.copy(t.max),this}makeEmpty(){return this.min.x=this.min.y=this.min.z=1/0,this.max.x=this.max.y=this.max.z=-1/0,this}isEmpty(){return this.max.x<this.min.x||this.max.y<this.min.y||this.max.z<this.min.z}getCenter(t){return this.isEmpty()?t.set(0,0,0):t.addVectors(this.min,this.max).multiplyScalar(.5)}getSize(t){return this.isEmpty()?t.set(0,0,0):t.subVectors(this.max,this.min)}expandByPoint(t){return this.min.min(t),this.max.max(t),this}expandByVector(t){return this.min.sub(t),this.max.add(t),this}expandByScalar(t){return this.min.addScalar(-t),this.max.addScalar(t),this}expandByObject(t,e=!1){t.updateWorldMatrix(!1,!1);let n=t.geometry;if(n!==void 0){let r=n.getAttribute("position");if(e===!0&&r!==void 0&&t.isInstancedMesh!==!0)for(let o=0,a=r.count;o<a;o++)t.isMesh===!0?t.getVertexPosition(o,Gt):Gt.fromBufferAttribute(r,o),Gt.applyMatrix4(t.matrixWorld),this.expandByPoint(Gt);else t.boundingBox!==void 0?(t.boundingBox===null&&t.computeBoundingBox(),En.copy(t.boundingBox)):(n.boundingBox===null&&n.computeBoundingBox(),En.copy(n.boundingBox)),En.applyMatrix4(t.matrixWorld),this.union(En)}let s=t.children;for(let r=0,o=s.length;r<o;r++)this.expandByObject(s[r],e);return this}containsPoint(t){return t.x>=this.min.x&&t.x<=this.max.x&&t.y>=this.min.y&&t.y<=this.max.y&&t.z>=this.min.z&&t.z<=this.max.z}containsBox(t){return this.min.x<=t.min.x&&t.max.x<=this.max.x&&this.min.y<=t.min.y&&t.max.y<=this.max.y&&this.min.z<=t.min.z&&t.max.z<=this.max.z}getParameter(t,e){return e.set((t.x-this.min.x)/(this.max.x-this.min.x),(t.y-this.min.y)/(this.max.y-this.min.y),(t.z-this.min.z)/(this.max.z-this.min.z))}intersectsBox(t){return t.max.x>=this.min.x&&t.min.x<=this.max.x&&t.max.y>=this.min.y&&t.min.y<=this.max.y&&t.max.z>=this.min.z&&t.min.z<=this.max.z}intersectsSphere(t){return this.clampPoint(t.center,Gt),Gt.distanceToSquared(t.center)<=t.radius*t.radius}intersectsPlane(t){let e,n;return t.normal.x>0?(e=t.normal.x*this.min.x,n=t.normal.x*this.max.x):(e=t.normal.x*this.max.x,n=t.normal.x*this.min.x),t.normal.y>0?(e+=t.normal.y*this.min.y,n+=t.normal.y*this.max.y):(e+=t.normal.y*this.max.y,n+=t.normal.y*this.min.y),t.normal.z>0?(e+=t.normal.z*this.min.z,n+=t.normal.z*this.max.z):(e+=t.normal.z*this.max.z,n+=t.normal.z*this.min.z),e<=-t.constant&&n>=-t.constant}intersectsTriangle(t){if(this.isEmpty())return!1;this.getCenter(en),Cn.subVectors(this.max,en),Le.subVectors(t.a,en),Ne.subVectors(t.b,en),De.subVectors(t.c,en),ee.subVectors(Ne,Le),ne.subVectors(De,Ne),de.subVectors(Le,De);let e=[0,-ee.z,ee.y,0,-ne.z,ne.y,0,-de.z,de.y,ee.z,0,-ee.x,ne.z,0,-ne.x,de.z,0,-de.x,-ee.y,ee.x,0,-ne.y,ne.x,0,-de.y,de.x,0];return!bi(e,Le,Ne,De,Cn)||(e=[1,0,0,0,1,0,0,0,1],!bi(e,Le,Ne,De,Cn))?!1:(Rn.crossVectors(ee,ne),e=[Rn.x,Rn.y,Rn.z],bi(e,Le,Ne,De,Cn))}clampPoint(t,e){return e.copy(t).clamp(this.min,this.max)}distanceToPoint(t){return this.clampPoint(t,Gt).distanceTo(t)}getBoundingSphere(t){return this.isEmpty()?t.makeEmpty():(this.getCenter(t.center),t.radius=this.getSize(Gt).length()*.5),t}intersect(t){return this.min.max(t.min),this.max.min(t.max),this.isEmpty()&&this.makeEmpty(),this}union(t){return this.min.min(t.min),this.max.max(t.max),this}applyMatrix4(t){return this.isEmpty()?this:(Yt[0].set(this.min.x,this.min.y,this.min.z).applyMatrix4(t),Yt[1].set(this.min.x,this.min.y,this.max.z).applyMatrix4(t),Yt[2].set(this.min.x,this.max.y,this.min.z).applyMatrix4(t),Yt[3].set(this.min.x,this.max.y,this.max.z).applyMatrix4(t),Yt[4].set(this.max.x,this.min.y,this.min.z).applyMatrix4(t),Yt[5].set(this.max.x,this.min.y,this.max.z).applyMatrix4(t),Yt[6].set(this.max.x,this.max.y,this.min.z).applyMatrix4(t),Yt[7].set(this.max.x,this.max.y,this.max.z).applyMatrix4(t),this.setFromPoints(Yt),this)}translate(t){return this.min.add(t),this.max.add(t),this}equals(t){return t.min.equals(this.min)&&t.max.equals(this.max)}toJSON(){return{min:this.min.toArray(),max:this.max.toArray()}}fromJSON(t){return this.min.fromArray(t.min),this.max.fromArray(t.max),this}},Yt=[new k,new k,new k,new k,new k,new k,new k,new k],Gt=new k,En=new ie,Le=new k,Ne=new k,De=new k,ee=new k,ne=new k,de=new k,en=new k,Cn=new k,Rn=new k,pe=new k;function bi(i,t,e,n,s){for(let r=0,o=i.length-3;r<=o;r+=3){pe.fromArray(i,r);let a=s.x*Math.abs(pe.x)+s.y*Math.abs(pe.y)+s.z*Math.abs(pe.z),c=t.dot(pe),l=e.dot(pe),h=n.dot(pe);if(Math.max(-Math.max(c,l,h),Math.min(c,l,h))>a)return!1}return!0}p(bi,"satForAxes");var lt=new k,In=new pt,ca=0,It=class extends me{static{p(this,"BufferAttribute")}constructor(t,e,n=!1){if(super(),Array.isArray(t))throw new TypeError("THREE.BufferAttribute: array should be a Typed Array.");this.isBufferAttribute=!0,Object.defineProperty(this,"id",{value:ca++}),this.name="",this.array=t,this.itemSize=e,this.count=t!==void 0?t.length/e:0,this.normalized=n,this.usage=Gi,this.updateRanges=[],this.gpuType=fr,this.version=0}onUploadCallback(){}set needsUpdate(t){t===!0&&this.version++}setUsage(t){return this.usage=t,this}addUpdateRange(t,e){this.updateRanges.push({start:t,count:e})}clearUpdateRanges(){this.updateRanges.length=0}copy(t){return this.name=t.name,this.array=new t.array.constructor(t.array),this.itemSize=t.itemSize,this.count=t.count,this.normalized=t.normalized,this.usage=t.usage,this.gpuType=t.gpuType,this}copyAt(t,e,n){t*=this.itemSize,n*=e.itemSize;for(let s=0,r=this.itemSize;s<r;s++)this.array[t+s]=e.array[n+s];return this}copyArray(t){return this.array.set(t),this}applyMatrix3(t){if(this.itemSize===2)for(let e=0,n=this.count;e<n;e++)In.fromBufferAttribute(this,e),In.applyMatrix3(t),this.setXY(e,In.x,In.y);else if(this.itemSize===3)for(let e=0,n=this.count;e<n;e++)lt.fromBufferAttribute(this,e),lt.applyMatrix3(t),this.setXYZ(e,lt.x,lt.y,lt.z);return this}applyMatrix4(t){for(let e=0,n=this.count;e<n;e++)lt.fromBufferAttribute(this,e),lt.applyMatrix4(t),this.setXYZ(e,lt.x,lt.y,lt.z);return this}applyNormalMatrix(t){for(let e=0,n=this.count;e<n;e++)lt.fromBufferAttribute(this,e),lt.applyNormalMatrix(t),this.setXYZ(e,lt.x,lt.y,lt.z);return this}transformDirection(t){for(let e=0,n=this.count;e<n;e++)lt.fromBufferAttribute(this,e),lt.transformDirection(t),this.setXYZ(e,lt.x,lt.y,lt.z);return this}set(t,e=0){return this.array.set(t,e),this}getComponent(t,e){let n=this.array[t*this.itemSize+e];return this.normalized&&(n=Qe(n,this.array)),n}setComponent(t,e,n){return this.normalized&&(n=wt(n,this.array)),this.array[t*this.itemSize+e]=n,this}getX(t){let e=this.array[t*this.itemSize];return this.normalized&&(e=Qe(e,this.array)),e}setX(t,e){return this.normalized&&(e=wt(e,this.array)),this.array[t*this.itemSize]=e,this}getY(t){let e=this.array[t*this.itemSize+1];return this.normalized&&(e=Qe(e,this.array)),e}setY(t,e){return this.normalized&&(e=wt(e,this.array)),this.array[t*this.itemSize+1]=e,this}getZ(t){let e=this.array[t*this.itemSize+2];return this.normalized&&(e=Qe(e,this.array)),e}setZ(t,e){return this.normalized&&(e=wt(e,this.array)),this.array[t*this.itemSize+2]=e,this}getW(t){let e=this.array[t*this.itemSize+3];return this.normalized&&(e=Qe(e,this.array)),e}setW(t,e){return this.normalized&&(e=wt(e,this.array)),this.array[t*this.itemSize+3]=e,this}setXY(t,e,n){return t*=this.itemSize,this.normalized&&(e=wt(e,this.array),n=wt(n,this.array)),this.array[t+0]=e,this.array[t+1]=n,this}setXYZ(t,e,n,s){return t*=this.itemSize,this.normalized&&(e=wt(e,this.array),n=wt(n,this.array),s=wt(s,this.array)),this.array[t+0]=e,this.array[t+1]=n,this.array[t+2]=s,this}setXYZW(t,e,n,s,r){return t*=this.itemSize,this.normalized&&(e=wt(e,this.array),n=wt(n,this.array),s=wt(s,this.array),r=wt(r,this.array)),this.array[t+0]=e,this.array[t+1]=n,this.array[t+2]=s,this.array[t+3]=r,this}onUpload(t){return this.onUploadCallback=t,this}clone(){return new this.constructor(this.array,this.itemSize).copy(this)}toJSON(){let t={itemSize:this.itemSize,type:this.array.constructor.name,array:Array.from(this.array),normalized:this.normalized};return this.name!==""&&(t.name=this.name),this.usage!==Gi&&(t.usage=this.usage),t}dispose(){this.dispatchEvent({type:"dispose"})}};var Vn=class extends It{static{p(this,"Uint16BufferAttribute")}constructor(t,e,n){super(new Uint16Array(t),e,n)}};var Gn=class extends It{static{p(this,"Uint32BufferAttribute")}constructor(t,e,n){super(new Uint32Array(t),e,n)}};var se=class extends It{static{p(this,"Float32BufferAttribute")}constructor(t,e,n){super(new Float32Array(t),e,n)}},la=new ie,nn=new k,Ai=new k,Hn=class{static{p(this,"Sphere")}constructor(t=new k,e=-1){this.isSphere=!0,this.center=t,this.radius=e}set(t,e){return this.center.copy(t),this.radius=e,this}setFromPoints(t,e){let n=this.center;e!==void 0?n.copy(e):la.setFromPoints(t).getCenter(n);let s=0;for(let r=0,o=t.length;r<o;r++)s=Math.max(s,n.distanceToSquared(t[r]));return this.radius=Math.sqrt(s),this}copy(t){return this.center.copy(t.center),this.radius=t.radius,this}isEmpty(){return this.radius<0}makeEmpty(){return this.center.set(0,0,0),this.radius=-1,this}containsPoint(t){return t.distanceToSquared(this.center)<=this.radius*this.radius}distanceToPoint(t){return t.distanceTo(this.center)-this.radius}intersectsSphere(t){let e=this.radius+t.radius;return t.center.distanceToSquared(this.center)<=e*e}intersectsBox(t){return t.intersectsSphere(this)}intersectsPlane(t){return Math.abs(t.distanceToPoint(this.center))<=this.radius}clampPoint(t,e){let n=this.center.distanceToSquared(t);return e.copy(t),n>this.radius*this.radius&&(e.sub(this.center).normalize(),e.multiplyScalar(this.radius).add(this.center)),e}getBoundingBox(t){return this.isEmpty()?(t.makeEmpty(),t):(t.set(this.center,this.center),t.expandByScalar(this.radius),t)}applyMatrix4(t){return this.center.applyMatrix4(t),this.radius=this.radius*t.getMaxScaleOnAxis(),this}translate(t){return this.center.add(t),this}expandByPoint(t){if(this.isEmpty())return this.center.copy(t),this.radius=0,this;nn.subVectors(t,this.center);let e=nn.lengthSq();if(e>this.radius*this.radius){let n=Math.sqrt(e),s=(n-this.radius)*.5;this.center.addScaledVector(nn,s/n),this.radius+=s}return this}union(t){return t.isEmpty()?this:this.isEmpty()?(this.copy(t),this):(this.center.equals(t.center)===!0?this.radius=Math.max(this.radius,t.radius):(Ai.subVectors(t.center,this.center).setLength(t.radius),this.expandByPoint(nn.copy(t.center).add(Ai)),this.expandByPoint(nn.copy(t.center).sub(Ai))),this)}equals(t){return t.center.equals(this.center)&&t.radius===this.radius}clone(){return new this.constructor().copy(this)}toJSON(){return{radius:this.radius,center:this.center.toArray()}}fromJSON(t){return this.radius=t.radius,this.center.fromArray(t.center),this}},ha=0,Ut=new mt,wi=new ge,Ue=new k,Rt=new ie,sn=new ie,ft=new k,ze=class i extends me{static{p(this,"BufferGeometry")}constructor(){super(),this.isBufferGeometry=!0,Object.defineProperty(this,"id",{value:ha++}),this.uuid=ti(),this.name="",this.type="BufferGeometry",this.index=null,this.indirect=null,this.indirectOffset=0,this.attributes={},this.morphAttributes={},this.morphTargetsRelative=!1,this.groups=[],this.boundingBox=null,this.boundingSphere=null,this.drawRange={start:0,count:1/0},this.userData={},this._transformed=!1}getIndex(){return this.index}setIndex(t){return Array.isArray(t)?this.index=new(Yo(t)?Gn:Vn)(t,1):this.index=t,this}setIndirect(t,e=0){return this.indirect=t,this.indirectOffset=e,this}getIndirect(){return this.indirect}getAttribute(t){return this.attributes[t]}setAttribute(t,e){return this.attributes[t]=e,this}deleteAttribute(t){return delete this.attributes[t],this}hasAttribute(t){return this.attributes[t]!==void 0}addGroup(t,e,n=0){this.groups.push({start:t,count:e,materialIndex:n})}clearGroups(){this.groups=[]}setDrawRange(t,e){this.drawRange.start=t,this.drawRange.count=e}applyMatrix4(t){let e=this.attributes.position;e!==void 0&&(e.applyMatrix4(t),e.needsUpdate=!0);let n=this.attributes.normal;if(n!==void 0){let r=new Y().getNormalMatrix(t);n.applyNormalMatrix(r),n.needsUpdate=!0}let s=this.attributes.tangent;return s!==void 0&&(s.transformDirection(t),s.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this._transformed=!0,this}applyQuaternion(t){return Ut.makeRotationFromQuaternion(t),this.applyMatrix4(Ut),this}rotateX(t){return Ut.makeRotationX(t),this.applyMatrix4(Ut),this}rotateY(t){return Ut.makeRotationY(t),this.applyMatrix4(Ut),this}rotateZ(t){return Ut.makeRotationZ(t),this.applyMatrix4(Ut),this}translate(t,e,n){return Ut.makeTranslation(t,e,n),this.applyMatrix4(Ut),this}scale(t,e,n){return Ut.makeScale(t,e,n),this.applyMatrix4(Ut),this}lookAt(t){return wi.lookAt(t),wi.updateMatrix(),this.applyMatrix4(wi.matrix),this}center(){return this.computeBoundingBox(),this.boundingBox.getCenter(Ue).negate(),this.translate(Ue.x,Ue.y,Ue.z),this}setFromPoints(t){let e=this.getAttribute("position");if(e===void 0){let n=[];for(let s=0,r=t.length;s<r;s++){let o=t[s];n.push(o.x,o.y,o.z||0)}this.setAttribute("position",new se(n,3))}else{let n=Math.min(t.length,e.count);for(let s=0;s<n;s++){let r=t[s];e.setXYZ(s,r.x,r.y,r.z||0)}t.length>e.count&&dt("BufferGeometry: Buffer size too small for points data. Use .dispose() and create a new geometry."),e.needsUpdate=!0}return this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new ie);let t=this.attributes.position,e=this.morphAttributes.position;if(t&&t.isGLBufferAttribute){st("BufferGeometry.computeBoundingBox(): GLBufferAttribute requires a manual bounding box.",this),this.boundingBox.set(new k(-1/0,-1/0,-1/0),new k(1/0,1/0,1/0));return}if(t!==void 0){if(this.boundingBox.setFromBufferAttribute(t),e)for(let n=0,s=e.length;n<s;n++){let r=e[n];Rt.setFromBufferAttribute(r),this.morphTargetsRelative?(ft.addVectors(this.boundingBox.min,Rt.min),this.boundingBox.expandByPoint(ft),ft.addVectors(this.boundingBox.max,Rt.max),this.boundingBox.expandByPoint(ft)):(this.boundingBox.expandByPoint(Rt.min),this.boundingBox.expandByPoint(Rt.max))}}else this.boundingBox.makeEmpty();(isNaN(this.boundingBox.min.x)||isNaN(this.boundingBox.min.y)||isNaN(this.boundingBox.min.z))&&st('BufferGeometry.computeBoundingBox(): Computed min/max have NaN values. The "position" attribute is likely to have NaN values.',this)}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new Hn);let t=this.attributes.position,e=this.morphAttributes.position;if(t&&t.isGLBufferAttribute){st("BufferGeometry.computeBoundingSphere(): GLBufferAttribute requires a manual bounding sphere.",this),this.boundingSphere.set(new k,1/0);return}if(t){let n=this.boundingSphere.center;if(Rt.setFromBufferAttribute(t),e)for(let r=0,o=e.length;r<o;r++){let a=e[r];sn.setFromBufferAttribute(a),this.morphTargetsRelative?(ft.addVectors(Rt.min,sn.min),Rt.expandByPoint(ft),ft.addVectors(Rt.max,sn.max),Rt.expandByPoint(ft)):(Rt.expandByPoint(sn.min),Rt.expandByPoint(sn.max))}Rt.getCenter(n);let s=0;for(let r=0,o=t.count;r<o;r++)ft.fromBufferAttribute(t,r),s=Math.max(s,n.distanceToSquared(ft));if(e)for(let r=0,o=e.length;r<o;r++){let a=e[r],c=this.morphTargetsRelative;for(let l=0,h=a.count;l<h;l++)ft.fromBufferAttribute(a,l),c&&(Ue.fromBufferAttribute(t,l),ft.add(Ue)),s=Math.max(s,n.distanceToSquared(ft))}this.boundingSphere.radius=Math.sqrt(s),isNaN(this.boundingSphere.radius)&&st('BufferGeometry.computeBoundingSphere(): Computed radius is NaN. The "position" attribute is likely to have NaN values.',this)}}computeTangents(){let t=this.index,e=this.attributes;if(t===null||e.position===void 0||e.normal===void 0||e.uv===void 0){st("BufferGeometry: .computeTangents() failed. Missing required attributes (index, position, normal or uv)");return}let n=e.position,s=e.normal,r=e.uv,o=this.getAttribute("tangent");(o===void 0||o.count!==n.count)&&(o=new It(new Float32Array(4*n.count),4),this.setAttribute("tangent",o));let a=[],c=[];for(let S=0;S<n.count;S++)a[S]=new k,c[S]=new k;let l=new k,h=new k,u=new k,f=new pt,d=new pt,m=new pt,g=new k,_=new k;function x(S,C,T){l.fromBufferAttribute(n,S),h.fromBufferAttribute(n,C),u.fromBufferAttribute(n,T),f.fromBufferAttribute(r,S),d.fromBufferAttribute(r,C),m.fromBufferAttribute(r,T),h.sub(l),u.sub(l),d.sub(f),m.sub(f);let D=1/(d.x*m.y-m.x*d.y);isFinite(D)&&(g.copy(h).multiplyScalar(m.y).addScaledVector(u,-d.y).multiplyScalar(D),_.copy(u).multiplyScalar(d.x).addScaledVector(h,-m.x).multiplyScalar(D),a[S].add(g),a[C].add(g),a[T].add(g),c[S].add(_),c[C].add(_),c[T].add(_))}p(x,"handleTriangle");let M=this.groups;M.length===0&&(M=[{start:0,count:t.count}]);for(let S=0,C=M.length;S<C;++S){let T=M[S],D=T.start,L=T.count;for(let P=D,R=D+L;P<R;P+=3)x(t.getX(P+0),t.getX(P+1),t.getX(P+2))}let y=new k,v=new k,b=new k,A=new k;function w(S){b.fromBufferAttribute(s,S),A.copy(b);let C=a[S];y.copy(C),y.sub(b.multiplyScalar(b.dot(C))).normalize(),v.crossVectors(A,C);let D=v.dot(c[S])<0?-1:1;o.setXYZW(S,y.x,y.y,y.z,D)}p(w,"handleVertex");for(let S=0,C=M.length;S<C;++S){let T=M[S],D=T.start,L=T.count;for(let P=D,R=D+L;P<R;P+=3)w(t.getX(P+0)),w(t.getX(P+1)),w(t.getX(P+2))}this._transformed=!0}computeVertexNormals(){let t=this.index,e=this.getAttribute("position");if(e!==void 0){let n=this.getAttribute("normal");if(n===void 0||n.count!==e.count)n=new It(new Float32Array(e.count*3),3),this.setAttribute("normal",n);else for(let f=0,d=n.count;f<d;f++)n.setXYZ(f,0,0,0);let s=new k,r=new k,o=new k,a=new k,c=new k,l=new k,h=new k,u=new k;if(t)for(let f=0,d=t.count;f<d;f+=3){let m=t.getX(f+0),g=t.getX(f+1),_=t.getX(f+2);s.fromBufferAttribute(e,m),r.fromBufferAttribute(e,g),o.fromBufferAttribute(e,_),h.subVectors(o,r),u.subVectors(s,r),h.cross(u),a.fromBufferAttribute(n,m),c.fromBufferAttribute(n,g),l.fromBufferAttribute(n,_),a.add(h),c.add(h),l.add(h),n.setXYZ(m,a.x,a.y,a.z),n.setXYZ(g,c.x,c.y,c.z),n.setXYZ(_,l.x,l.y,l.z)}else for(let f=0,d=e.count;f<d;f+=3)s.fromBufferAttribute(e,f+0),r.fromBufferAttribute(e,f+1),o.fromBufferAttribute(e,f+2),h.subVectors(o,r),u.subVectors(s,r),h.cross(u),n.setXYZ(f+0,h.x,h.y,h.z),n.setXYZ(f+1,h.x,h.y,h.z),n.setXYZ(f+2,h.x,h.y,h.z);this.normalizeNormals(),n.needsUpdate=!0}}normalizeNormals(){let t=this.attributes.normal;for(let e=0,n=t.count;e<n;e++)ft.fromBufferAttribute(t,e),ft.normalize(),t.setXYZ(e,ft.x,ft.y,ft.z)}toNonIndexed(){function t(a,c){let l=a.array,h=a.itemSize,u=a.normalized,f=new l.constructor(c.length*h),d=0,m=0;for(let g=0,_=c.length;g<_;g++){a.isInterleavedBufferAttribute?d=c[g]*a.data.stride+a.offset:d=c[g]*h;for(let x=0;x<h;x++)f[m++]=l[d++]}return new It(f,h,u)}if(p(t,"convertBufferAttribute"),this.index===null)return dt("BufferGeometry.toNonIndexed(): BufferGeometry is already non-indexed."),this;let e=new i,n=this.index.array,s=this.attributes;for(let a in s){let c=s[a],l=t(c,n);e.setAttribute(a,l)}let r=this.morphAttributes;for(let a in r){let c=[],l=r[a];for(let h=0,u=l.length;h<u;h++){let f=l[h],d=t(f,n);c.push(d)}e.morphAttributes[a]=c}e.morphTargetsRelative=this.morphTargetsRelative;let o=this.groups;for(let a=0,c=o.length;a<c;a++){let l=o[a];e.addGroup(l.start,l.count,l.materialIndex)}return e}toJSON(){let t={metadata:{version:4.7,type:"BufferGeometry",generator:"BufferGeometry.toJSON"}};if(t.uuid=this.uuid,t.type=this.parameters!==void 0&&this._transformed===!0?"BufferGeometry":this.type,this.name!==""&&(t.name=this.name),Object.keys(this.userData).length>0&&(t.userData=this.userData),this.parameters!==void 0&&this._transformed!==!0){let c=this.parameters;for(let l in c)c[l]!==void 0&&(t[l]=c[l]);return t}t.data={attributes:{}};let e=this.index;e!==null&&(t.data.index={type:e.array.constructor.name,array:Array.prototype.slice.call(e.array)});let n=this.attributes;for(let c in n){let l=n[c];t.data.attributes[c]=l.toJSON(t.data)}let s={},r=!1;for(let c in this.morphAttributes){let l=this.morphAttributes[c],h=[];for(let u=0,f=l.length;u<f;u++){let d=l[u];h.push(d.toJSON(t.data))}h.length>0&&(s[c]=h,r=!0)}r&&(t.data.morphAttributes=s,t.data.morphTargetsRelative=this.morphTargetsRelative);let o=this.groups;o.length>0&&(t.data.groups=JSON.parse(JSON.stringify(o)));let a=this.boundingSphere;return a!==null&&(t.data.boundingSphere=a.toJSON()),t}clone(){return new this.constructor().copy(this)}copy(t){this.index=null,this.attributes={},this.morphAttributes={},this.groups=[],this.boundingBox=null,this.boundingSphere=null;let e={};this.name=t.name;let n=t.index;n!==null&&this.setIndex(n.clone());let s=t.attributes;for(let l in s){let h=s[l];this.setAttribute(l,h.clone(e))}let r=t.morphAttributes;for(let l in r){let h=[],u=r[l];for(let f=0,d=u.length;f<d;f++)h.push(u[f].clone(e));this.morphAttributes[l]=h}this.morphTargetsRelative=t.morphTargetsRelative;let o=t.groups;for(let l=0,h=o.length;l<h;l++){let u=o[l];this.addGroup(u.start,u.count,u.materialIndex)}let a=t.boundingBox;a!==null&&(this.boundingBox=a.clone());let c=t.boundingSphere;return c!==null&&(this.boundingSphere=c.clone()),this.drawRange.start=t.drawRange.start,this.drawRange.count=t.drawRange.count,this.userData=t.userData,this._transformed=t._transformed,this}dispose(){this.dispatchEvent({type:"dispose"})}};function ua(i,t,e=2){let n=t&&t.length,s=n?t[0]*e:i.length,r=gr(i,0,s,e,!0),o=[];if(!r||r.next===r.prev)return o;let a,c,l;if(n&&(r=ga(i,t,r,e)),i.length>80*e){a=i[0],c=i[1];let h=a,u=c;for(let f=e;f<s;f+=e){let d=i[f],m=i[f+1];d<a&&(a=d),m<c&&(c=m),d>h&&(h=d),m>u&&(u=m)}l=Math.max(h-a,u-c),l=l!==0?32767/l:0}return hn(r,o,e,a,c,l,0),o}p(ua,"earcut");function gr(i,t,e,n,s){let r;if(s===Ea(i,t,e,n)>0)for(let o=t;o<e;o+=n)r=js(o/n|0,i[o],i[o+1],r);else for(let o=e-n;o>=t;o-=n)r=js(o/n|0,i[o],i[o+1],r);return r&&ke(r,r.next)&&(fn(r),r=r.next),r}p(gr,"linkedList");function xe(i,t){if(!i)return i;t||(t=i);let e=i,n;do if(n=!1,!e.steiner&&(ke(e,e.next)||rt(e.prev,e,e.next)===0)){if(fn(e),e=t=e.prev,e===e.next)break;n=!0}else e=e.next;while(n||e!==t);return t}p(xe,"filterPoints");function hn(i,t,e,n,s,r,o){if(!i)return;!o&&r&&Ma(i,n,s,r);let a=i;for(;i.prev!==i.next;){let c=i.prev,l=i.next;if(r?da(i,n,s,r):fa(i)){t.push(c.i,i.i,l.i),fn(i),i=l.next,a=l.next;continue}if(i=l,i===a){o?o===1?(i=pa(xe(i),t),hn(i,t,e,n,s,r,2)):o===2&&ma(i,t,e,n,s,r):hn(xe(i),t,e,n,s,r,1);break}}}p(hn,"earcutLinked");function fa(i){let t=i.prev,e=i,n=i.next;if(rt(t,e,n)>=0)return!1;let s=t.x,r=e.x,o=n.x,a=t.y,c=e.y,l=n.y,h=Math.min(s,r,o),u=Math.min(a,c,l),f=Math.max(s,r,o),d=Math.max(a,c,l),m=n.next;for(;m!==t;){if(m.x>=h&&m.x<=f&&m.y>=u&&m.y<=d&&an(s,a,r,c,o,l,m.x,m.y)&&rt(m.prev,m,m.next)>=0)return!1;m=m.next}return!0}p(fa,"isEar");function da(i,t,e,n){let s=i.prev,r=i,o=i.next;if(rt(s,r,o)>=0)return!1;let a=s.x,c=r.x,l=o.x,h=s.y,u=r.y,f=o.y,d=Math.min(a,c,l),m=Math.min(h,u,f),g=Math.max(a,c,l),_=Math.max(h,u,f),x=qi(d,m,t,e,n),M=qi(g,_,t,e,n),y=i.prevZ,v=i.nextZ;for(;y&&y.z>=x&&v&&v.z<=M;){if(y.x>=d&&y.x<=g&&y.y>=m&&y.y<=_&&y!==s&&y!==o&&an(a,h,c,u,l,f,y.x,y.y)&&rt(y.prev,y,y.next)>=0||(y=y.prevZ,v.x>=d&&v.x<=g&&v.y>=m&&v.y<=_&&v!==s&&v!==o&&an(a,h,c,u,l,f,v.x,v.y)&&rt(v.prev,v,v.next)>=0))return!1;v=v.nextZ}for(;y&&y.z>=x;){if(y.x>=d&&y.x<=g&&y.y>=m&&y.y<=_&&y!==s&&y!==o&&an(a,h,c,u,l,f,y.x,y.y)&&rt(y.prev,y,y.next)>=0)return!1;y=y.prevZ}for(;v&&v.z<=M;){if(v.x>=d&&v.x<=g&&v.y>=m&&v.y<=_&&v!==s&&v!==o&&an(a,h,c,u,l,f,v.x,v.y)&&rt(v.prev,v,v.next)>=0)return!1;v=v.nextZ}return!0}p(da,"isEarHashed");function pa(i,t){let e=i;do{let n=e.prev,s=e.next.next;!ke(n,s)&&_r(n,e,e.next,s)&&un(n,s)&&un(s,n)&&(t.push(n.i,e.i,s.i),fn(e),fn(e.next),e=i=s),e=e.next}while(e!==i);return xe(e)}p(pa,"cureLocalIntersections");function ma(i,t,e,n,s,r){let o=i;do{let a=o.next.next;for(;a!==o.prev;){if(o.i!==a.i&&Aa(o,a)){let c=yr(o,a);o=xe(o,o.next),c=xe(c,c.next),hn(o,t,e,n,s,r,0),hn(c,t,e,n,s,r,0);return}a=a.next}o=o.next}while(o!==i)}p(ma,"splitEarcut");function ga(i,t,e,n){let s=[];for(let r=0,o=t.length;r<o;r++){let a=t[r]*n,c=r<o-1?t[r+1]*n:i.length,l=gr(i,a,c,n,!1);l===l.next&&(l.steiner=!0),s.push(ba(l))}s.sort(xa);for(let r=0;r<s.length;r++)e=_a(s[r],e);return e}p(ga,"eliminateHoles");function xa(i,t){let e=i.x-t.x;if(e===0&&(e=i.y-t.y,e===0)){let n=(i.next.y-i.y)/(i.next.x-i.x),s=(t.next.y-t.y)/(t.next.x-t.x);e=n-s}return e}p(xa,"compareXYSlope");function _a(i,t){let e=ya(i,t);if(!e)return t;let n=yr(e,i);return xe(n,n.next),xe(e,e.next)}p(_a,"eliminateHole");function ya(i,t){let e=t,n=i.x,s=i.y,r=-1/0,o;if(ke(i,e))return e;do{if(ke(i,e.next))return e.next;if(s<=e.y&&s>=e.next.y&&e.next.y!==e.y){let u=e.x+(s-e.y)*(e.next.x-e.x)/(e.next.y-e.y);if(u<=n&&u>r&&(r=u,o=e.x<e.next.x?e:e.next,u===n))return o}e=e.next}while(e!==t);if(!o)return null;let a=o,c=o.x,l=o.y,h=1/0;e=o;do{if(n>=e.x&&e.x>=c&&n!==e.x&&xr(s<l?n:r,s,c,l,s<l?r:n,s,e.x,e.y)){let u=Math.abs(s-e.y)/(n-e.x);un(e,i)&&(u<h||u===h&&(e.x>o.x||e.x===o.x&&va(o,e)))&&(o=e,h=u)}e=e.next}while(e!==a);return o}p(ya,"findHoleBridge");function va(i,t){return rt(i.prev,i,t.prev)<0&&rt(t.next,i,i.next)<0}p(va,"sectorContainsSector");function Ma(i,t,e,n){let s=i;do s.z===0&&(s.z=qi(s.x,s.y,t,e,n)),s.prevZ=s.prev,s.nextZ=s.next,s=s.next;while(s!==i);s.prevZ.nextZ=null,s.prevZ=null,Sa(s)}p(Ma,"indexCurve");function Sa(i){let t,e=1;do{let n=i,s;i=null;let r=null;for(t=0;n;){t++;let o=n,a=0;for(let l=0;l<e&&(a++,o=o.nextZ,!!o);l++);let c=e;for(;a>0||c>0&&o;)a!==0&&(c===0||!o||n.z<=o.z)?(s=n,n=n.nextZ,a--):(s=o,o=o.nextZ,c--),r?r.nextZ=s:i=s,s.prevZ=r,r=s;n=o}r.nextZ=null,e*=2}while(t>1);return i}p(Sa,"sortLinked");function qi(i,t,e,n,s){return i=(i-e)*s|0,t=(t-n)*s|0,i=(i|i<<8)&16711935,i=(i|i<<4)&252645135,i=(i|i<<2)&858993459,i=(i|i<<1)&1431655765,t=(t|t<<8)&16711935,t=(t|t<<4)&252645135,t=(t|t<<2)&858993459,t=(t|t<<1)&1431655765,i|t<<1}p(qi,"zOrder");function ba(i){let t=i,e=i;do(t.x<e.x||t.x===e.x&&t.y<e.y)&&(e=t),t=t.next;while(t!==i);return e}p(ba,"getLeftmost");function xr(i,t,e,n,s,r,o,a){return(s-o)*(t-a)>=(i-o)*(r-a)&&(i-o)*(n-a)>=(e-o)*(t-a)&&(e-o)*(r-a)>=(s-o)*(n-a)}p(xr,"pointInTriangle");function an(i,t,e,n,s,r,o,a){return!(i===o&&t===a)&&xr(i,t,e,n,s,r,o,a)}p(an,"pointInTriangleExceptFirst");function Aa(i,t){return i.next.i!==t.i&&i.prev.i!==t.i&&!wa(i,t)&&(un(i,t)&&un(t,i)&&Ta(i,t)&&(rt(i.prev,i,t.prev)||rt(i,t.prev,t))||ke(i,t)&&rt(i.prev,i,i.next)>0&&rt(t.prev,t,t.next)>0)}p(Aa,"isValidDiagonal");function rt(i,t,e){return(t.y-i.y)*(e.x-t.x)-(t.x-i.x)*(e.y-t.y)}p(rt,"area");function ke(i,t){return i.x===t.x&&i.y===t.y}p(ke,"equals");function _r(i,t,e,n){let s=Ln(rt(i,t,e)),r=Ln(rt(i,t,n)),o=Ln(rt(e,n,i)),a=Ln(rt(e,n,t));return!!(s!==r&&o!==a||s===0&&Pn(i,e,t)||r===0&&Pn(i,n,t)||o===0&&Pn(e,i,n)||a===0&&Pn(e,t,n))}p(_r,"intersects");function Pn(i,t,e){return t.x<=Math.max(i.x,e.x)&&t.x>=Math.min(i.x,e.x)&&t.y<=Math.max(i.y,e.y)&&t.y>=Math.min(i.y,e.y)}p(Pn,"onSegment");function Ln(i){return i>0?1:i<0?-1:0}p(Ln,"sign");function wa(i,t){let e=i;do{if(e.i!==i.i&&e.next.i!==i.i&&e.i!==t.i&&e.next.i!==t.i&&_r(e,e.next,i,t))return!0;e=e.next}while(e!==i);return!1}p(wa,"intersectsPolygon");function un(i,t){return rt(i.prev,i,i.next)<0?rt(i,t,i.next)>=0&&rt(i,i.prev,t)>=0:rt(i,t,i.prev)<0||rt(i,i.next,t)<0}p(un,"locallyInside");function Ta(i,t){let e=i,n=!1,s=(i.x+t.x)/2,r=(i.y+t.y)/2;do e.y>r!=e.next.y>r&&e.next.y!==e.y&&s<(e.next.x-e.x)*(r-e.y)/(e.next.y-e.y)+e.x&&(n=!n),e=e.next;while(e!==i);return n}p(Ta,"middleInside");function yr(i,t){let e=$i(i.i,i.x,i.y),n=$i(t.i,t.x,t.y),s=i.next,r=t.prev;return i.next=t,t.prev=i,e.next=s,s.prev=e,n.next=e,e.prev=n,r.next=n,n.prev=r,n}p(yr,"splitPolygon");function js(i,t,e,n){let s=$i(i,t,e);return n?(s.next=n.next,s.prev=n,n.next.prev=s,n.next=s):(s.prev=s,s.next=s),s}p(js,"insertNode");function fn(i){i.next.prev=i.prev,i.prev.next=i.next,i.prevZ&&(i.prevZ.nextZ=i.nextZ),i.nextZ&&(i.nextZ.prevZ=i.prevZ)}p(fn,"removeNode");function $i(i,t,e){return{i,x:t,y:e,prev:null,next:null,z:0,prevZ:null,nextZ:null,steiner:!1}}p($i,"createNode");function Ea(i,t,e,n){let s=0;for(let r=t,o=e-n;r<e;r+=n)s+=(i[o]-i[r])*(i[r+1]+i[o+1]),o=r;return s}p(Ea,"signedArea");var Yi=class{static{p(this,"Earcut")}static triangulate(t,e,n=2){return ua(t,e,n)}},dn=class i{static{p(this,"ShapeUtils")}static area(t){let e=t.length,n=0;for(let s=e-1,r=0;r<e;s=r++)n+=t[s].x*t[r].y-t[r].x*t[s].y;return n*.5}static isClockWise(t){return i.area(t)<0}static triangulateShape(t,e){let n=[],s=[],r=[];Qs(t),tr(n,t);let o=t.length;e.forEach(Qs);for(let c=0;c<e.length;c++)s.push(o),o+=e[c].length,tr(n,e[c]);let a=Yi.triangulate(n,s);for(let c=0;c<a.length;c+=3)r.push(a.slice(c,c+3));return r}};function Qs(i){let t=i.length;t>2&&i[t-1].equals(i[0])&&i.pop()}p(Qs,"removeDupEndPts");function tr(i,t){for(let e=0;e<t.length;e++)i.push(t[e].x),i.push(t[e].y)}p(tr,"addContour");function vr(i){let t={};for(let e in i){t[e]={};for(let n in i[e]){let s=i[e][n];if(er(s))s.isRenderTargetTexture?(dt("UniformsUtils: Textures of render targets cannot be cloned via cloneUniforms() or mergeUniforms()."),t[e][n]=null):t[e][n]=s.clone();else if(Array.isArray(s))if(er(s[0])){let r=[];for(let o=0,a=s.length;o<a;o++)r[o]=s[o].clone();t[e][n]=r}else t[e][n]=s.slice();else t[e][n]=s}}return t}p(vr,"cloneUniforms");function St(i){let t={};for(let e=0;e<i.length;e++){let n=vr(i[e]);for(let s in n)t[s]=n[s]}return t}p(St,"mergeUniforms");function er(i){return i&&(i.isColor||i.isMatrix3||i.isMatrix4||i.isVector2||i.isVector3||i.isVector4||i.isTexture||i.isQuaternion)}p(er,"isThreeObject");function Nn(i,t){return!i||i.constructor===t?i:typeof t.BYTES_PER_ELEMENT=="number"?new t(i):Array.prototype.slice.call(i)}p(Nn,"convertArray");var re=class{static{p(this,"Interpolant")}constructor(t,e,n,s){this.parameterPositions=t,this._cachedIndex=0,this.resultBuffer=s!==void 0?s:new e.constructor(n),this.sampleValues=e,this.valueSize=n,this.settings=null,this.DefaultSettings_={}}evaluate(t){let e=this.parameterPositions,n=this._cachedIndex,s=e[n],r=e[n-1];n:{t:{let o;e:{i:if(!(t<s)){for(let a=n+2;;){if(s===void 0){if(t<r)break i;return n=e.length,this._cachedIndex=n,this.copySampleValue_(n-1)}if(n===a)break;if(r=s,s=e[++n],t<s)break t}o=e.length;break e}if(!(t>=r)){let a=e[1];t<a&&(n=2,r=a);for(let c=n-2;;){if(r===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(n===c)break;if(s=r,r=e[--n-1],t>=r)break t}o=n,n=0;break e}break n}for(;n<o;){let a=n+o>>>1;t<e[a]?o=a:n=a+1}if(s=e[n],r=e[n-1],r===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(s===void 0)return n=e.length,this._cachedIndex=n,this.copySampleValue_(n-1)}this._cachedIndex=n,this.intervalChanged_(n,r,s)}return this.interpolate_(n,r,t,s)}getSettings_(){return this.settings||this.DefaultSettings_}copySampleValue_(t){let e=this.resultBuffer,n=this.sampleValues,s=this.valueSize,r=t*s;for(let o=0;o!==s;++o)e[o]=n[r+o];return e}interpolate_(){throw new Error("THREE.Interpolant: Call to abstract method.")}intervalChanged_(){}},Wn=class extends re{static{p(this,"CubicInterpolant")}constructor(t,e,n,s){super(t,e,n,s),this._weightPrev=-0,this._offsetPrev=-0,this._weightNext=-0,this._offsetNext=-0,this.DefaultSettings_={endingStart:Oi,endingEnd:Oi}}intervalChanged_(t,e,n){let s=this.parameterPositions,r=t-2,o=t+1,a=s[r],c=s[o];if(a===void 0)switch(this.getSettings_().endingStart){case Bi:r=t,a=2*e-n;break;case zi:r=s.length-2,a=e+s[r]-s[r+1];break;default:r=t,a=n}if(c===void 0)switch(this.getSettings_().endingEnd){case Bi:o=t,c=2*n-e;break;case zi:o=1,c=n+s[1]-s[0];break;default:o=t-1,c=e}let l=(n-e)*.5,h=this.valueSize;this._weightPrev=l/(e-a),this._weightNext=l/(c-n),this._offsetPrev=r*h,this._offsetNext=o*h}interpolate_(t,e,n,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,h=this._offsetPrev,u=this._offsetNext,f=this._weightPrev,d=this._weightNext,m=(n-e)/(s-e),g=m*m,_=g*m,x=-f*_+2*f*g-f*m,M=(1+f)*_+(-1.5-2*f)*g+(-.5+f)*m+1,y=(-1-d)*_+(1.5+d)*g+.5*m,v=d*_-d*g;for(let b=0;b!==a;++b)r[b]=x*o[h+b]+M*o[l+b]+y*o[c+b]+v*o[u+b];return r}},Xn=class extends re{static{p(this,"LinearInterpolant")}constructor(t,e,n,s){super(t,e,n,s)}interpolate_(t,e,n,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,h=(n-e)/(s-e),u=1-h;for(let f=0;f!==a;++f)r[f]=o[l+f]*u+o[c+f]*h;return r}},qn=class extends re{static{p(this,"DiscreteInterpolant")}constructor(t,e,n,s){super(t,e,n,s)}interpolate_(t){return this.copySampleValue_(t-1)}},$n=class extends re{static{p(this,"BezierInterpolant")}interpolate_(t,e,n,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,h=this.inTangents,u=this.outTangents;if(!h||!u){let m=(n-e)/(s-e),g=1-m;for(let _=0;_!==a;++_)r[_]=o[l+_]*g+o[c+_]*m;return r}let f=a*2,d=t-1;for(let m=0;m!==a;++m){let g=o[l+m],_=o[c+m],x=d*f+m*2,M=u[x],y=u[x+1],v=t*f+m*2,b=h[v],A=h[v+1],w=(n-e)/(s-e),S,C,T,D,L;for(let P=0;P<8;P++){S=w*w,C=S*w,T=1-w,D=T*T,L=D*T;let I=L*e+3*D*w*M+3*T*S*b+C*s-n;if(Math.abs(I)<1e-10)break;let E=3*D*(M-e)+6*T*w*(b-M)+3*S*(s-b);if(Math.abs(E)<1e-10)break;w=w-I/E,w=Math.max(0,Math.min(1,w))}r[m]=L*g+3*D*w*y+3*T*S*A+C*_}return r}},Pt=class{static{p(this,"KeyframeTrack")}constructor(t,e,n,s){if(t===void 0)throw new Error("THREE.KeyframeTrack: track name is undefined");if(e===void 0||e.length===0)throw new Error("THREE.KeyframeTrack: no keyframes in track named "+t);this.name=t,this.times=Nn(e,this.TimeBufferType),this.values=Nn(n,this.ValueBufferType),this.setInterpolation(s||this.DefaultInterpolation)}static toJSON(t){let e=t.constructor,n;if(e.toJSON!==this.toJSON)n=e.toJSON(t);else{n={name:t.name,times:Nn(t.times,Array),values:Nn(t.values,Array)};let s=t.getInterpolation();s!==t.DefaultInterpolation&&(n.interpolation=s)}return n.type=t.ValueTypeName,n}InterpolantFactoryMethodDiscrete(t){return new qn(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodLinear(t){return new Xn(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodSmooth(t){return new Wn(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodBezier(t){let e=new $n(this.times,this.values,this.getValueSize(),t);return this.settings&&(e.inTangents=this.settings.inTangents,e.outTangents=this.settings.outTangents),e}setInterpolation(t){let e;switch(t){case cn:e=this.InterpolantFactoryMethodDiscrete;break;case Fn:e=this.InterpolantFactoryMethodLinear;break;case Dn:e=this.InterpolantFactoryMethodSmooth;break;case Fi:e=this.InterpolantFactoryMethodBezier;break}if(e===void 0){let n="unsupported interpolation for "+this.ValueTypeName+" keyframe track named "+this.name;if(this.createInterpolant===void 0)if(t!==this.DefaultInterpolation)this.setInterpolation(this.DefaultInterpolation);else throw new Error(n);return dt("KeyframeTrack:",n),this}return this.createInterpolant=e,this}getInterpolation(){switch(this.createInterpolant){case this.InterpolantFactoryMethodDiscrete:return cn;case this.InterpolantFactoryMethodLinear:return Fn;case this.InterpolantFactoryMethodSmooth:return Dn;case this.InterpolantFactoryMethodBezier:return Fi}}getValueSize(){return this.values.length/this.times.length}shift(t){if(t!==0){let e=this.times;for(let n=0,s=e.length;n!==s;++n)e[n]+=t}return this}scale(t){if(t!==1){let e=this.times;for(let n=0,s=e.length;n!==s;++n)e[n]*=t}return this}trim(t,e){let n=this.times,s=n.length,r=0,o=s-1;for(;r!==s&&n[r]<t;)++r;for(;o!==-1&&n[o]>e;)--o;if(++o,r!==0||o!==s){r>=o&&(o=Math.max(o,1),r=o-1);let a=this.getValueSize();this.times=n.slice(r,o),this.values=this.values.slice(r*a,o*a)}return this}validate(){let t=!0,e=this.getValueSize();e-Math.floor(e)!==0&&(st("KeyframeTrack: Invalid value size in track.",this),t=!1);let n=this.times,s=this.values,r=n.length;r===0&&(st("KeyframeTrack: Track is empty.",this),t=!1);let o=null;for(let a=0;a!==r;a++){let c=n[a];if(typeof c=="number"&&isNaN(c)){st("KeyframeTrack: Time is not a valid number.",this,a,c),t=!1;break}if(o!==null&&o>c){st("KeyframeTrack: Out of order keys.",this,a,c,o),t=!1;break}o=c}if(s!==void 0&&Zo(s))for(let a=0,c=s.length;a!==c;++a){let l=s[a];if(isNaN(l)){st("KeyframeTrack: Value is not a valid number.",this,a,l),t=!1;break}}return t}optimize(){let t=this.times.slice(),e=this.values.slice(),n=this.getValueSize(),s=this.getInterpolation()===Dn,r=t.length-1,o=1;for(let a=1;a<r;++a){let c=!1,l=t[a],h=t[a+1];if(l!==h&&(a!==1||l!==t[0]))if(s)c=!0;else{let u=a*n,f=u-n,d=u+n;for(let m=0;m!==n;++m){let g=e[u+m];if(g!==e[f+m]||g!==e[d+m]){c=!0;break}}}if(c){if(a!==o){t[o]=t[a];let u=a*n,f=o*n;for(let d=0;d!==n;++d)e[f+d]=e[u+d]}++o}}if(r>0){t[o]=t[r];for(let a=r*n,c=o*n,l=0;l!==n;++l)e[c+l]=e[a+l];++o}return o!==t.length?(this.times=t.slice(0,o),this.values=e.slice(0,o*n)):(this.times=t,this.values=e),this}clone(){let t=this.times.slice(),e=this.values.slice(),n=this.constructor,s=new n(this.name,t,e);return s.createInterpolant=this.createInterpolant,s}};Pt.prototype.ValueTypeName="";Pt.prototype.TimeBufferType=Float32Array;Pt.prototype.ValueBufferType=Float32Array;Pt.prototype.DefaultInterpolation=Fn;var oe=class extends Pt{static{p(this,"BooleanKeyframeTrack")}constructor(t,e,n){super(t,e,n)}};oe.prototype.ValueTypeName="bool";oe.prototype.ValueBufferType=Array;oe.prototype.DefaultInterpolation=cn;oe.prototype.InterpolantFactoryMethodLinear=void 0;oe.prototype.InterpolantFactoryMethodSmooth=void 0;var Yn=class extends Pt{static{p(this,"ColorKeyframeTrack")}constructor(t,e,n,s){super(t,e,n,s)}};Yn.prototype.ValueTypeName="color";var Zn=class extends Pt{static{p(this,"NumberKeyframeTrack")}constructor(t,e,n,s){super(t,e,n,s)}};Zn.prototype.ValueTypeName="number";var Jn=class extends re{static{p(this,"QuaternionLinearInterpolant")}constructor(t,e,n,s){super(t,e,n,s)}interpolate_(t,e,n,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=(n-e)/(s-e),l=t*a;for(let h=l+a;l!==h;l+=4)Ht.slerpFlat(r,0,o,l-a,o,l,c);return r}},pn=class extends Pt{static{p(this,"QuaternionKeyframeTrack")}constructor(t,e,n,s){super(t,e,n,s)}InterpolantFactoryMethodLinear(t){return new Jn(this.times,this.values,this.getValueSize(),t)}};pn.prototype.ValueTypeName="quaternion";pn.prototype.InterpolantFactoryMethodSmooth=void 0;var ae=class extends Pt{static{p(this,"StringKeyframeTrack")}constructor(t,e,n){super(t,e,n)}};ae.prototype.ValueTypeName="string";ae.prototype.ValueBufferType=Array;ae.prototype.DefaultInterpolation=cn;ae.prototype.InterpolantFactoryMethodLinear=void 0;ae.prototype.InterpolantFactoryMethodSmooth=void 0;var Kn=class extends Pt{static{p(this,"VectorKeyframeTrack")}constructor(t,e,n,s){super(t,e,n,s)}};Kn.prototype.ValueTypeName="vector";var jn=class{static{p(this,"LoadingManager")}constructor(t,e,n){let s=this,r=!1,o=0,a=0,c,l=[];this.onStart=void 0,this.onLoad=t,this.onProgress=e,this.onError=n,this._abortController=null,this.itemStart=function(h){a++,r===!1&&s.onStart!==void 0&&s.onStart(h,o,a),r=!0},this.itemEnd=function(h){o++,s.onProgress!==void 0&&s.onProgress(h,o,a),o===a&&(r=!1,s.onLoad!==void 0&&s.onLoad())},this.itemError=function(h){s.onError!==void 0&&s.onError(h)},this.resolveURL=function(h){return h=h.normalize("NFC"),c?c(h):h},this.setURLModifier=function(h){return c=h,this},this.addHandler=function(h,u){return l.push(h,u),this},this.removeHandler=function(h){let u=l.indexOf(h);return u!==-1&&l.splice(u,2),this},this.getHandler=function(h){for(let u=0,f=l.length;u<f;u+=2){let d=l[u],m=l[u+1];if(d.global&&(d.lastIndex=0),d.test(h))return m}return null},this.abort=function(){return this.abortController.abort(),this._abortController=null,this}}get abortController(){return this._abortController||(this._abortController=new AbortController),this._abortController}},Mr=new jn,Qn=class{static{p(this,"Loader")}constructor(t){this.manager=t!==void 0?t:Mr,this.crossOrigin="anonymous",this.withCredentials=!1,this.path="",this.resourcePath="",this.requestHeader={},typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}load(){}loadAsync(t,e){let n=this;return new Promise(function(s,r){n.load(t,s,e,r)})}parse(){}setCrossOrigin(t){return this.crossOrigin=t,this}setWithCredentials(t){return this.withCredentials=t,this}setPath(t){return this.path=t,this}setResourcePath(t){return this.resourcePath=t,this}setRequestHeader(t){return this.requestHeader=t,this}abort(){return this}};Qn.DEFAULT_MATERIAL_NAME="__DEFAULT";var as="\\[\\]\\.:\\/",Ca=new RegExp("["+as+"]","g"),cs="[^"+as+"]",Ra="[^"+as.replace("\\.","")+"]",Ia=/((?:WC+[\/:])*)/.source.replace("WC",cs),Pa=/(WCOD+)?/.source.replace("WCOD",Ra),La=/(?:\.(WC+)(?:\[(.+)\])?)?/.source.replace("WC",cs),Na=/\.(WC+)(?:\[(.+)\])?/.source.replace("WC",cs),Da=new RegExp("^"+Ia+Pa+La+Na+"$"),Ua=["material","materials","bones","map"],Zi=class{static{p(this,"Composite")}constructor(t,e,n){let s=n||tt.parseTrackName(e);this._targetGroup=t,this._bindings=t.subscribe_(e,s)}getValue(t,e){this.bind();let n=this._targetGroup.nCachedObjects_,s=this._bindings[n];s!==void 0&&s.getValue(t,e)}setValue(t,e){let n=this._bindings;for(let s=this._targetGroup.nCachedObjects_,r=n.length;s!==r;++s)n[s].setValue(t,e)}bind(){let t=this._bindings;for(let e=this._targetGroup.nCachedObjects_,n=t.length;e!==n;++e)t[e].bind()}unbind(){let t=this._bindings;for(let e=this._targetGroup.nCachedObjects_,n=t.length;e!==n;++e)t[e].unbind()}},tt=class i{static{p(this,"PropertyBinding")}constructor(t,e,n){this.path=e,this.parsedPath=n||i.parseTrackName(e),this.node=i.findNode(t,this.parsedPath.nodeName),this.rootNode=t,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}static create(t,e,n){return t&&t.isAnimationObjectGroup?new i.Composite(t,e,n):new i(t,e,n)}static sanitizeNodeName(t){return t.replace(/\s/g,"_").replace(Ca,"")}static parseTrackName(t){let e=Da.exec(t);if(e===null)throw new Error("THREE.PropertyBinding: Cannot parse trackName: "+t);let n={nodeName:e[2],objectName:e[3],objectIndex:e[4],propertyName:e[5],propertyIndex:e[6]},s=n.nodeName&&n.nodeName.lastIndexOf(".");if(s!==void 0&&s!==-1){let r=n.nodeName.substring(s+1);Ua.indexOf(r)!==-1&&(n.nodeName=n.nodeName.substring(0,s),n.objectName=r)}if(n.propertyName===null||n.propertyName.length===0)throw new Error("THREE.PropertyBinding: can not parse propertyName from trackName: "+t);return n}static findNode(t,e){if(e===void 0||e===""||e==="."||e===-1||e===t.name||e===t.uuid)return t;if(t.skeleton){let n=t.skeleton.getBoneByName(e);if(n!==void 0)return n}if(t.children){let n=p(function(r){for(let o=0;o<r.length;o++){let a=r[o];if(a.name===e||a.uuid===e)return a;let c=n(a.children);if(c)return c}return null},"searchNodeSubtree"),s=n(t.children);if(s)return s}return null}_getValue_unavailable(){}_setValue_unavailable(){}_getValue_direct(t,e){t[e]=this.targetObject[this.propertyName]}_getValue_array(t,e){let n=this.resolvedProperty;for(let s=0,r=n.length;s!==r;++s)t[e++]=n[s]}_getValue_arrayElement(t,e){t[e]=this.resolvedProperty[this.propertyIndex]}_getValue_toArray(t,e){this.resolvedProperty.toArray(t,e)}_setValue_direct(t,e){this.targetObject[this.propertyName]=t[e]}_setValue_direct_setNeedsUpdate(t,e){this.targetObject[this.propertyName]=t[e],this.targetObject.needsUpdate=!0}_setValue_direct_setMatrixWorldNeedsUpdate(t,e){this.targetObject[this.propertyName]=t[e],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_array(t,e){let n=this.resolvedProperty;for(let s=0,r=n.length;s!==r;++s)n[s]=t[e++]}_setValue_array_setNeedsUpdate(t,e){let n=this.resolvedProperty;for(let s=0,r=n.length;s!==r;++s)n[s]=t[e++];this.targetObject.needsUpdate=!0}_setValue_array_setMatrixWorldNeedsUpdate(t,e){let n=this.resolvedProperty;for(let s=0,r=n.length;s!==r;++s)n[s]=t[e++];this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_arrayElement(t,e){this.resolvedProperty[this.propertyIndex]=t[e]}_setValue_arrayElement_setNeedsUpdate(t,e){this.resolvedProperty[this.propertyIndex]=t[e],this.targetObject.needsUpdate=!0}_setValue_arrayElement_setMatrixWorldNeedsUpdate(t,e){this.resolvedProperty[this.propertyIndex]=t[e],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_fromArray(t,e){this.resolvedProperty.fromArray(t,e)}_setValue_fromArray_setNeedsUpdate(t,e){this.resolvedProperty.fromArray(t,e),this.targetObject.needsUpdate=!0}_setValue_fromArray_setMatrixWorldNeedsUpdate(t,e){this.resolvedProperty.fromArray(t,e),this.targetObject.matrixWorldNeedsUpdate=!0}_getValue_unbound(t,e){this.bind(),this.getValue(t,e)}_setValue_unbound(t,e){this.bind(),this.setValue(t,e)}bind(){let t=this.node,e=this.parsedPath,n=e.objectName,s=e.propertyName,r=e.propertyIndex;if(t||(t=i.findNode(this.rootNode,e.nodeName),this.node=t),this.getValue=this._getValue_unavailable,this.setValue=this._setValue_unavailable,!t){dt("PropertyBinding: No target node found for track: "+this.path+".");return}if(n){let l=e.objectIndex;switch(n){case"materials":if(!t.material){st("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!t.material.materials){st("PropertyBinding: Can not bind to material.materials as node.material does not have a materials array.",this);return}t=t.material.materials;break;case"bones":if(!t.skeleton){st("PropertyBinding: Can not bind to bones as node does not have a skeleton.",this);return}t=t.skeleton.bones;for(let h=0;h<t.length;h++)if(t[h].name===l){l=h;break}break;case"map":if("map"in t){t=t.map;break}if(!t.material){st("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!t.material.map){st("PropertyBinding: Can not bind to material.map as node.material does not have a map.",this);return}t=t.material.map;break;default:if(t[n]===void 0){st("PropertyBinding: Can not bind to objectName of node undefined.",this);return}t=t[n]}if(l!==void 0){if(t[l]===void 0){st("PropertyBinding: Trying to bind to objectIndex of objectName, but is undefined.",this,t);return}t=t[l]}}let o=t[s];if(o===void 0){let l=e.nodeName;st("PropertyBinding: Trying to update property for track: "+l+"."+s+" but it wasn't found.",t);return}let a=this.Versioning.None;this.targetObject=t,t.isMaterial===!0?a=this.Versioning.NeedsUpdate:t.isObject3D===!0&&(a=this.Versioning.MatrixWorldNeedsUpdate);let c=this.BindingType.Direct;if(r!==void 0){if(s==="morphTargetInfluences"){if(!t.geometry){st("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.",this);return}if(!t.geometry.morphAttributes){st("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.morphAttributes.",this);return}t.morphTargetDictionary[r]!==void 0&&(r=t.morphTargetDictionary[r])}c=this.BindingType.ArrayElement,this.resolvedProperty=o,this.propertyIndex=r}else o.fromArray!==void 0&&o.toArray!==void 0?(c=this.BindingType.HasFromToArray,this.resolvedProperty=o):Array.isArray(o)?(c=this.BindingType.EntireArray,this.resolvedProperty=o):this.propertyName=s;this.getValue=this.GetterByBindingType[c],this.setValue=this.SetterByBindingTypeAndVersioning[c][a]}unbind(){this.node=null,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}};tt.Composite=Zi;tt.prototype.BindingType={Direct:0,EntireArray:1,ArrayElement:2,HasFromToArray:3};tt.prototype.Versioning={None:0,NeedsUpdate:1,MatrixWorldNeedsUpdate:2};tt.prototype.GetterByBindingType=[tt.prototype._getValue_direct,tt.prototype._getValue_array,tt.prototype._getValue_arrayElement,tt.prototype._getValue_toArray];tt.prototype.SetterByBindingTypeAndVersioning=[[tt.prototype._setValue_direct,tt.prototype._setValue_direct_setNeedsUpdate,tt.prototype._setValue_direct_setMatrixWorldNeedsUpdate],[tt.prototype._setValue_array,tt.prototype._setValue_array_setNeedsUpdate,tt.prototype._setValue_array_setMatrixWorldNeedsUpdate],[tt.prototype._setValue_arrayElement,tt.prototype._setValue_arrayElement_setNeedsUpdate,tt.prototype._setValue_arrayElement_setMatrixWorldNeedsUpdate],[tt.prototype._setValue_fromArray,tt.prototype._setValue_fromArray_setNeedsUpdate,tt.prototype._setValue_fromArray_setMatrixWorldNeedsUpdate]];var gf=new Float32Array(1);var Ji=class i{static{p(this,"Matrix2")}static{i.prototype.isMatrix2=!0}constructor(t,e,n,s){this.elements=[1,0,0,1],t!==void 0&&this.set(t,e,n,s)}identity(){return this.set(1,0,0,1),this}fromArray(t,e=0){for(let n=0;n<4;n++)this.elements[n]=t[n+e];return this}set(t,e,n,s){let r=this.elements;return r[0]=t,r[2]=e,r[1]=n,r[3]=s,this}};typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("register",{detail:{revision:"185"}}));typeof window<"u"&&(window.__THREE__?dt("WARNING: Multiple instances of Three.js being imported."):window.__THREE__="185");var Fa=`#ifdef USE_ALPHAHASH
	if ( diffuseColor.a < getAlphaHashThreshold( vPosition ) ) discard;
#endif`,Oa=`#ifdef USE_ALPHAHASH
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
#endif`,Ba=`#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, vAlphaMapUv ).g;
#endif`,za=`#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,ka=`#ifdef USE_ALPHATEST
	#ifdef ALPHA_TO_COVERAGE
	diffuseColor.a = smoothstep( alphaTest, alphaTest + fwidth( diffuseColor.a ), diffuseColor.a );
	if ( diffuseColor.a == 0.0 ) discard;
	#else
	if ( diffuseColor.a < alphaTest ) discard;
	#endif
#endif`,Va=`#ifdef USE_ALPHATEST
	uniform float alphaTest;
#endif`,Ga=`#ifdef USE_AOMAP
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
#endif`,Ha=`#ifdef USE_AOMAP
	uniform sampler2D aoMap;
	uniform float aoMapIntensity;
#endif`,Wa=`#ifdef USE_BATCHING
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
#endif`,Xa=`#ifdef USE_BATCHING
	mat4 batchingMatrix = getBatchingMatrix( getIndirectIndex( gl_DrawID ) );
#endif`,qa=`vec3 transformed = vec3( position );
#ifdef USE_ALPHAHASH
	vPosition = vec3( position );
#endif`,$a=`vec3 objectNormal = vec3( normal );
#ifdef USE_TANGENT
	vec3 objectTangent = vec3( tangent.xyz );
#endif`,Ya=`float G_BlinnPhong_Implicit( ) {
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
} // validated`,Za=`#ifdef USE_IRIDESCENCE
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
#endif`,Ja=`#ifdef USE_BUMPMAP
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
#endif`,Ka=`#if NUM_CLIPPING_PLANES > 0
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
#endif`,ja=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
	uniform vec4 clippingPlanes[ NUM_CLIPPING_PLANES ];
#endif`,Qa=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
#endif`,tc=`#if NUM_CLIPPING_PLANES > 0
	vClipPosition = - mvPosition.xyz;
#endif`,ec=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	diffuseColor *= vColor;
#endif`,nc=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#endif`,ic=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	varying vec4 vColor;
#endif`,sc=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
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
#endif`,rc=`#define PI 3.141592653589793
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
} // validated`,oc=`#ifdef ENVMAP_TYPE_CUBE_UV
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
#endif`,ac=`vec3 transformedNormal = objectNormal;
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
#endif`,cc=`#ifdef USE_DISPLACEMENTMAP
	uniform sampler2D displacementMap;
	uniform float displacementScale;
	uniform float displacementBias;
#endif`,lc=`#ifdef USE_DISPLACEMENTMAP
	transformed += normalize( objectNormal ) * ( texture2D( displacementMap, vDisplacementMapUv ).x * displacementScale + displacementBias );
#endif`,hc=`#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
	#ifdef DECODE_VIDEO_TEXTURE_EMISSIVE
		emissiveColor = sRGBTransferEOTF( emissiveColor );
	#endif
	totalEmissiveRadiance *= emissiveColor.rgb;
#endif`,uc=`#ifdef USE_EMISSIVEMAP
	uniform sampler2D emissiveMap;
#endif`,fc="gl_FragColor = linearToOutputTexel( gl_FragColor );",dc=`vec4 LinearTransferOETF( in vec4 value ) {
	return value;
}
vec4 sRGBTransferEOTF( in vec4 value ) {
	return vec4( mix( pow( value.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), value.rgb * 0.0773993808, vec3( lessThanEqual( value.rgb, vec3( 0.04045 ) ) ) ), value.a );
}
vec4 sRGBTransferOETF( in vec4 value ) {
	return vec4( mix( pow( value.rgb, vec3( 0.41666 ) ) * 1.055 - vec3( 0.055 ), value.rgb * 12.92, vec3( lessThanEqual( value.rgb, vec3( 0.0031308 ) ) ) ), value.a );
}`,pc=`#ifdef USE_ENVMAP
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
#endif`,mc=`#ifdef USE_ENVMAP
	uniform float envMapIntensity;
	uniform mat3 envMapRotation;
	#ifdef ENVMAP_TYPE_CUBE
		uniform samplerCube envMap;
	#else
		uniform sampler2D envMap;
	#endif
#endif`,gc=`#ifdef USE_ENVMAP
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
#endif`,xc=`#ifdef USE_ENVMAP
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		
		varying vec3 vWorldPosition;
	#else
		varying vec3 vReflect;
		uniform float refractionRatio;
	#endif
#endif`,_c=`#ifdef USE_ENVMAP
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
#endif`,yc=`#ifdef USE_FOG
	vFogDepth = - mvPosition.z;
#endif`,vc=`#ifdef USE_FOG
	varying float vFogDepth;
#endif`,Mc=`#ifdef USE_FOG
	#ifdef FOG_EXP2
		float fogFactor = 1.0 - exp( - fogDensity * fogDensity * vFogDepth * vFogDepth );
	#else
		float fogFactor = smoothstep( fogNear, fogFar, vFogDepth );
	#endif
	gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );
#endif`,Sc=`#ifdef USE_FOG
	uniform vec3 fogColor;
	varying float vFogDepth;
	#ifdef FOG_EXP2
		uniform float fogDensity;
	#else
		uniform float fogNear;
		uniform float fogFar;
	#endif
#endif`,bc=`#ifdef USE_GRADIENTMAP
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
}`,Ac=`#ifdef USE_LIGHTMAP
	uniform sampler2D lightMap;
	uniform float lightMapIntensity;
#endif`,wc=`LambertMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularStrength = specularStrength;`,Tc=`varying vec3 vViewPosition;
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
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Lambert`,Ec=`uniform bool receiveShadow;
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
#include <lightprobes_pars_fragment>`,Cc=`#ifdef USE_ENVMAP
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
#endif`,Rc=`ToonMaterial material;
material.diffuseColor = diffuseColor.rgb;`,Ic=`varying vec3 vViewPosition;
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
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Toon`,Pc=`BlinnPhongMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularColor = specular;
material.specularShininess = shininess;
material.specularStrength = specularStrength;`,Lc=`varying vec3 vViewPosition;
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
#define RE_IndirectDiffuse		RE_IndirectDiffuse_BlinnPhong`,Nc=`PhysicalMaterial material;
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
#endif`,Dc=`uniform sampler2D dfgLUT;
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
}`,Uc=`
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
#endif`,Fc=`#if defined( RE_IndirectDiffuse )
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
#endif`,Oc=`#if defined( RE_IndirectDiffuse )
	#if defined( LAMBERT ) || defined( PHONG )
		irradiance += iblIrradiance;
	#endif
	RE_IndirectDiffuse( irradiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif
#if defined( RE_IndirectSpecular )
	RE_IndirectSpecular( radiance, iblIrradiance, clearcoatRadiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif`,Bc=`#ifdef USE_LIGHT_PROBES_GRID
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
#endif`,zc=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	gl_FragDepth = vIsPerspective == 0.0 ? gl_FragCoord.z : log2( vFragDepth ) * logDepthBufFC * 0.5;
#endif`,kc=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	uniform float logDepthBufFC;
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,Vc=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,Gc=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	vFragDepth = 1.0 + gl_Position.w;
	vIsPerspective = float( isPerspectiveMatrix( projectionMatrix ) );
#endif`,Hc=`#ifdef USE_MAP
	vec4 sampledDiffuseColor = texture2D( map, vMapUv );
	#ifdef DECODE_VIDEO_TEXTURE
		sampledDiffuseColor = sRGBTransferEOTF( sampledDiffuseColor );
	#endif
	diffuseColor *= sampledDiffuseColor;
#endif`,Wc=`#ifdef USE_MAP
	uniform sampler2D map;
#endif`,Xc=`#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
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
#endif`,qc=`#if defined( USE_POINTS_UV )
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
#endif`,$c=`float metalnessFactor = metalness;
#ifdef USE_METALNESSMAP
	vec4 texelMetalness = texture2D( metalnessMap, vMetalnessMapUv );
	metalnessFactor *= texelMetalness.b;
#endif`,Yc=`#ifdef USE_METALNESSMAP
	uniform sampler2D metalnessMap;
#endif`,Zc=`#ifdef USE_INSTANCING_MORPH
	float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	float morphTargetBaseInfluence = texelFetch( morphTexture, ivec2( 0, gl_InstanceID ), 0 ).r;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		morphTargetInfluences[i] =  texelFetch( morphTexture, ivec2( i + 1, gl_InstanceID ), 0 ).r;
	}
#endif`,Jc=`#if defined( USE_MORPHCOLORS )
	vColor *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		#if defined( USE_COLOR_ALPHA )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ) * morphTargetInfluences[ i ];
		#elif defined( USE_COLOR )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ).rgb * morphTargetInfluences[ i ];
		#endif
	}
#endif`,Kc=`#ifdef USE_MORPHNORMALS
	objectNormal *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) objectNormal += getMorph( gl_VertexID, i, 1 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,jc=`#ifdef USE_MORPHTARGETS
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
#endif`,Qc=`#ifdef USE_MORPHTARGETS
	transformed *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) transformed += getMorph( gl_VertexID, i, 0 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,tl=`float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;
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
vec3 nonPerturbedNormal = normal;`,el=`#ifdef USE_NORMALMAP_OBJECTSPACE
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
#endif`,nl=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,il=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,sl=`#ifndef FLAT_SHADED
	vNormal = normalize( transformedNormal );
	#ifdef USE_TANGENT
		vTangent = normalize( transformedTangent );
		vBitangent = normalize( cross( vNormal, vTangent ) * tangent.w );
		#ifdef FLIP_SIDED
			vBitangent = - vBitangent;
		#endif
	#endif
#endif`,rl=`#ifdef USE_NORMALMAP
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
#endif`,ol=`#ifdef USE_CLEARCOAT
	vec3 clearcoatNormal = nonPerturbedNormal;
#endif`,al=`#ifdef USE_CLEARCOAT_NORMALMAP
	vec3 clearcoatMapN = texture2D( clearcoatNormalMap, vClearcoatNormalMapUv ).xyz * 2.0 - 1.0;
	clearcoatMapN.xy *= clearcoatNormalScale;
	clearcoatNormal = normalize( tbn2 * clearcoatMapN );
#endif`,cl=`#ifdef USE_CLEARCOATMAP
	uniform sampler2D clearcoatMap;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform sampler2D clearcoatNormalMap;
	uniform vec2 clearcoatNormalScale;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform sampler2D clearcoatRoughnessMap;
#endif`,ll=`#ifdef USE_IRIDESCENCEMAP
	uniform sampler2D iridescenceMap;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform sampler2D iridescenceThicknessMap;
#endif`,hl=`#ifdef OPAQUE
diffuseColor.a = 1.0;
#endif
#ifdef USE_TRANSMISSION
diffuseColor.a *= material.transmissionAlpha;
#endif
gl_FragColor = vec4( outgoingLight, diffuseColor.a );`,ul=`vec3 packNormalToRGB( const in vec3 normal ) {
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
}`,fl=`#ifdef PREMULTIPLIED_ALPHA
	gl_FragColor.rgb *= gl_FragColor.a;
#endif`,dl=`vec4 mvPosition = vec4( transformed, 1.0 );
#ifdef USE_BATCHING
	mvPosition = batchingMatrix * mvPosition;
#endif
#ifdef USE_INSTANCING
	mvPosition = instanceMatrix * mvPosition;
#endif
mvPosition = modelViewMatrix * mvPosition;
gl_Position = projectionMatrix * mvPosition;`,pl=`#ifdef DITHERING
	gl_FragColor.rgb = dithering( gl_FragColor.rgb );
#endif`,ml=`#ifdef DITHERING
	vec3 dithering( vec3 color ) {
		float grid_position = rand( gl_FragCoord.xy );
		vec3 dither_shift_RGB = vec3( 0.25 / 255.0, -0.25 / 255.0, 0.25 / 255.0 );
		dither_shift_RGB = mix( 2.0 * dither_shift_RGB, -2.0 * dither_shift_RGB, grid_position );
		return color + dither_shift_RGB;
	}
#endif`,gl=`float roughnessFactor = roughness;
#ifdef USE_ROUGHNESSMAP
	vec4 texelRoughness = texture2D( roughnessMap, vRoughnessMapUv );
	roughnessFactor *= texelRoughness.g;
#endif`,xl=`#ifdef USE_ROUGHNESSMAP
	uniform sampler2D roughnessMap;
#endif`,_l=`#if NUM_SPOT_LIGHT_COORDS > 0
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
#endif`,yl=`#if NUM_SPOT_LIGHT_COORDS > 0
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
#endif`,vl=`#if ( defined( USE_SHADOWMAP ) && ( NUM_DIR_LIGHT_SHADOWS > 0 || NUM_POINT_LIGHT_SHADOWS > 0 ) ) || ( NUM_SPOT_LIGHT_COORDS > 0 )
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
#endif`,Ml=`float getShadowMask() {
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
}`,Sl=`#ifdef USE_SKINNING
	mat4 boneMatX = getBoneMatrix( skinIndex.x );
	mat4 boneMatY = getBoneMatrix( skinIndex.y );
	mat4 boneMatZ = getBoneMatrix( skinIndex.z );
	mat4 boneMatW = getBoneMatrix( skinIndex.w );
#endif`,bl=`#ifdef USE_SKINNING
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
#endif`,Al=`#ifdef USE_SKINNING
	vec4 skinVertex = bindMatrix * vec4( transformed, 1.0 );
	vec4 skinned = vec4( 0.0 );
	skinned += boneMatX * skinVertex * skinWeight.x;
	skinned += boneMatY * skinVertex * skinWeight.y;
	skinned += boneMatZ * skinVertex * skinWeight.z;
	skinned += boneMatW * skinVertex * skinWeight.w;
	transformed = ( bindMatrixInverse * skinned ).xyz;
#endif`,wl=`#ifdef USE_SKINNING
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
#endif`,Tl=`float specularStrength;
#ifdef USE_SPECULARMAP
	vec4 texelSpecular = texture2D( specularMap, vSpecularMapUv );
	specularStrength = texelSpecular.r;
#else
	specularStrength = 1.0;
#endif`,El=`#ifdef USE_SPECULARMAP
	uniform sampler2D specularMap;
#endif`,Cl=`#if defined( TONE_MAPPING )
	gl_FragColor.rgb = toneMapping( gl_FragColor.rgb );
#endif`,Rl=`#ifndef saturate
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
vec3 CustomToneMapping( vec3 color ) { return color; }`,Il=`#ifdef USE_TRANSMISSION
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
#endif`,Pl=`#ifdef USE_TRANSMISSION
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
#endif`,Ll=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
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
#endif`,Nl=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
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
#endif`,Dl=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
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
#endif`,Ul=`#if defined( USE_ENVMAP ) || defined( DISTANCE ) || defined ( USE_SHADOWMAP ) || defined ( USE_TRANSMISSION ) || NUM_SPOT_LIGHT_COORDS > 0
	vec4 worldPosition = vec4( transformed, 1.0 );
	#ifdef USE_BATCHING
		worldPosition = batchingMatrix * worldPosition;
	#endif
	#ifdef USE_INSTANCING
		worldPosition = instanceMatrix * worldPosition;
	#endif
	worldPosition = modelMatrix * worldPosition;
#endif`,Fl=`varying vec2 vUv;
uniform mat3 uvTransform;
void main() {
	vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	gl_Position = vec4( position.xy, 1.0, 1.0 );
}`,Ol=`uniform sampler2D t2D;
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
}`,Bl=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,zl=`#ifdef ENVMAP_TYPE_CUBE
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
}`,kl=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,Vl=`uniform samplerCube tCube;
uniform float tFlip;
uniform float opacity;
varying vec3 vWorldDirection;
void main() {
	vec4 texColor = textureCube( tCube, vec3( tFlip * vWorldDirection.x, vWorldDirection.yz ) );
	gl_FragColor = texColor;
	gl_FragColor.a *= opacity;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Gl=`#include <common>
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
}`,Hl=`#if DEPTH_PACKING == 3200
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
}`,Wl=`#define DISTANCE
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
}`,Xl=`#define DISTANCE
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
}`,ql=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
}`,$l=`uniform sampler2D tEquirect;
varying vec3 vWorldDirection;
#include <common>
void main() {
	vec3 direction = normalize( vWorldDirection );
	vec2 sampleUV = equirectUv( direction );
	gl_FragColor = texture2D( tEquirect, sampleUV );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Yl=`uniform float scale;
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
}`,Zl=`uniform vec3 diffuse;
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
}`,Jl=`#include <common>
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
}`,Kl=`uniform vec3 diffuse;
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
}`,jl=`#define LAMBERT
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
}`,Ql=`#define LAMBERT
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
}`,th=`#define MATCAP
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
}`,eh=`#define MATCAP
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
}`,nh=`#define NORMAL
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
}`,ih=`#define NORMAL
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
}`,sh=`#define PHONG
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
}`,rh=`#define PHONG
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
}`,oh=`#define STANDARD
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
}`,ah=`#define STANDARD
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
}`,ch=`#define TOON
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
}`,lh=`#define TOON
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
}`,hh=`uniform float size;
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
}`,uh=`uniform vec3 diffuse;
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
}`,fh=`#include <common>
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
}`,dh=`uniform vec3 color;
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
}`,ph=`uniform float rotation;
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
}`,mh=`uniform vec3 diffuse;
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
}`,Z={alphahash_fragment:Fa,alphahash_pars_fragment:Oa,alphamap_fragment:Ba,alphamap_pars_fragment:za,alphatest_fragment:ka,alphatest_pars_fragment:Va,aomap_fragment:Ga,aomap_pars_fragment:Ha,batching_pars_vertex:Wa,batching_vertex:Xa,begin_vertex:qa,beginnormal_vertex:$a,bsdfs:Ya,iridescence_fragment:Za,bumpmap_pars_fragment:Ja,clipping_planes_fragment:Ka,clipping_planes_pars_fragment:ja,clipping_planes_pars_vertex:Qa,clipping_planes_vertex:tc,color_fragment:ec,color_pars_fragment:nc,color_pars_vertex:ic,color_vertex:sc,common:rc,cube_uv_reflection_fragment:oc,defaultnormal_vertex:ac,displacementmap_pars_vertex:cc,displacementmap_vertex:lc,emissivemap_fragment:hc,emissivemap_pars_fragment:uc,colorspace_fragment:fc,colorspace_pars_fragment:dc,envmap_fragment:pc,envmap_common_pars_fragment:mc,envmap_pars_fragment:gc,envmap_pars_vertex:xc,envmap_physical_pars_fragment:Cc,envmap_vertex:_c,fog_vertex:yc,fog_pars_vertex:vc,fog_fragment:Mc,fog_pars_fragment:Sc,gradientmap_pars_fragment:bc,lightmap_pars_fragment:Ac,lights_lambert_fragment:wc,lights_lambert_pars_fragment:Tc,lights_pars_begin:Ec,lights_toon_fragment:Rc,lights_toon_pars_fragment:Ic,lights_phong_fragment:Pc,lights_phong_pars_fragment:Lc,lights_physical_fragment:Nc,lights_physical_pars_fragment:Dc,lights_fragment_begin:Uc,lights_fragment_maps:Fc,lights_fragment_end:Oc,lightprobes_pars_fragment:Bc,logdepthbuf_fragment:zc,logdepthbuf_pars_fragment:kc,logdepthbuf_pars_vertex:Vc,logdepthbuf_vertex:Gc,map_fragment:Hc,map_pars_fragment:Wc,map_particle_fragment:Xc,map_particle_pars_fragment:qc,metalnessmap_fragment:$c,metalnessmap_pars_fragment:Yc,morphinstance_vertex:Zc,morphcolor_vertex:Jc,morphnormal_vertex:Kc,morphtarget_pars_vertex:jc,morphtarget_vertex:Qc,normal_fragment_begin:tl,normal_fragment_maps:el,normal_pars_fragment:nl,normal_pars_vertex:il,normal_vertex:sl,normalmap_pars_fragment:rl,clearcoat_normal_fragment_begin:ol,clearcoat_normal_fragment_maps:al,clearcoat_pars_fragment:cl,iridescence_pars_fragment:ll,opaque_fragment:hl,packing:ul,premultiplied_alpha_fragment:fl,project_vertex:dl,dithering_fragment:pl,dithering_pars_fragment:ml,roughnessmap_fragment:gl,roughnessmap_pars_fragment:xl,shadowmap_pars_fragment:_l,shadowmap_pars_vertex:yl,shadowmap_vertex:vl,shadowmask_pars_fragment:Ml,skinbase_vertex:Sl,skinning_pars_vertex:bl,skinning_vertex:Al,skinnormal_vertex:wl,specularmap_fragment:Tl,specularmap_pars_fragment:El,tonemapping_fragment:Cl,tonemapping_pars_fragment:Rl,transmission_fragment:Il,transmission_pars_fragment:Pl,uv_pars_fragment:Ll,uv_pars_vertex:Nl,uv_vertex:Dl,worldpos_vertex:Ul,background_vert:Fl,background_frag:Ol,backgroundCube_vert:Bl,backgroundCube_frag:zl,cube_vert:kl,cube_frag:Vl,depth_vert:Gl,depth_frag:Hl,distance_vert:Wl,distance_frag:Xl,equirect_vert:ql,equirect_frag:$l,linedashed_vert:Yl,linedashed_frag:Zl,meshbasic_vert:Jl,meshbasic_frag:Kl,meshlambert_vert:jl,meshlambert_frag:Ql,meshmatcap_vert:th,meshmatcap_frag:eh,meshnormal_vert:nh,meshnormal_frag:ih,meshphong_vert:sh,meshphong_frag:rh,meshphysical_vert:oh,meshphysical_frag:ah,meshtoon_vert:ch,meshtoon_frag:lh,points_vert:hh,points_frag:uh,shadow_vert:fh,shadow_frag:dh,sprite_vert:ph,sprite_frag:mh},V={common:{diffuse:{value:new gt(16777215)},opacity:{value:1},map:{value:null},mapTransform:{value:new Y},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0}},specularmap:{specularMap:{value:null},specularMapTransform:{value:new Y}},envmap:{envMap:{value:null},envMapRotation:{value:new Y},reflectivity:{value:1},ior:{value:1.5},refractionRatio:{value:.98},dfgLUT:{value:null}},aomap:{aoMap:{value:null},aoMapIntensity:{value:1},aoMapTransform:{value:new Y}},lightmap:{lightMap:{value:null},lightMapIntensity:{value:1},lightMapTransform:{value:new Y}},bumpmap:{bumpMap:{value:null},bumpMapTransform:{value:new Y},bumpScale:{value:1}},normalmap:{normalMap:{value:null},normalMapTransform:{value:new Y},normalScale:{value:new pt(1,1)}},displacementmap:{displacementMap:{value:null},displacementMapTransform:{value:new Y},displacementScale:{value:1},displacementBias:{value:0}},emissivemap:{emissiveMap:{value:null},emissiveMapTransform:{value:new Y}},metalnessmap:{metalnessMap:{value:null},metalnessMapTransform:{value:new Y}},roughnessmap:{roughnessMap:{value:null},roughnessMapTransform:{value:new Y}},gradientmap:{gradientMap:{value:null}},fog:{fogDensity:{value:25e-5},fogNear:{value:1},fogFar:{value:2e3},fogColor:{value:new gt(16777215)}},lights:{ambientLightColor:{value:[]},lightProbe:{value:[]},directionalLights:{value:[],properties:{direction:{},color:{}}},directionalLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},directionalShadowMatrix:{value:[]},spotLights:{value:[],properties:{color:{},position:{},direction:{},distance:{},coneCos:{},penumbraCos:{},decay:{}}},spotLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},spotLightMap:{value:[]},spotLightMatrix:{value:[]},pointLights:{value:[],properties:{color:{},position:{},decay:{},distance:{}}},pointLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{},shadowCameraNear:{},shadowCameraFar:{}}},pointShadowMatrix:{value:[]},hemisphereLights:{value:[],properties:{direction:{},skyColor:{},groundColor:{}}},rectAreaLights:{value:[],properties:{color:{},position:{},width:{},height:{}}},ltc_1:{value:null},ltc_2:{value:null},probesSH:{value:null},probesMin:{value:new k},probesMax:{value:new k},probesResolution:{value:new k}},points:{diffuse:{value:new gt(16777215)},opacity:{value:1},size:{value:1},scale:{value:1},map:{value:null},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0},uvTransform:{value:new Y}},sprite:{diffuse:{value:new gt(16777215)},opacity:{value:1},center:{value:new pt(.5,.5)},rotation:{value:0},map:{value:null},mapTransform:{value:new Y},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0}}},Sr={basic:{uniforms:St([V.common,V.specularmap,V.envmap,V.aomap,V.lightmap,V.fog]),vertexShader:Z.meshbasic_vert,fragmentShader:Z.meshbasic_frag},lambert:{uniforms:St([V.common,V.specularmap,V.envmap,V.aomap,V.lightmap,V.emissivemap,V.bumpmap,V.normalmap,V.displacementmap,V.fog,V.lights,{emissive:{value:new gt(0)},envMapIntensity:{value:1}}]),vertexShader:Z.meshlambert_vert,fragmentShader:Z.meshlambert_frag},phong:{uniforms:St([V.common,V.specularmap,V.envmap,V.aomap,V.lightmap,V.emissivemap,V.bumpmap,V.normalmap,V.displacementmap,V.fog,V.lights,{emissive:{value:new gt(0)},specular:{value:new gt(1118481)},shininess:{value:30},envMapIntensity:{value:1}}]),vertexShader:Z.meshphong_vert,fragmentShader:Z.meshphong_frag},standard:{uniforms:St([V.common,V.envmap,V.aomap,V.lightmap,V.emissivemap,V.bumpmap,V.normalmap,V.displacementmap,V.roughnessmap,V.metalnessmap,V.fog,V.lights,{emissive:{value:new gt(0)},roughness:{value:1},metalness:{value:0},envMapIntensity:{value:1}}]),vertexShader:Z.meshphysical_vert,fragmentShader:Z.meshphysical_frag},toon:{uniforms:St([V.common,V.aomap,V.lightmap,V.emissivemap,V.bumpmap,V.normalmap,V.displacementmap,V.gradientmap,V.fog,V.lights,{emissive:{value:new gt(0)}}]),vertexShader:Z.meshtoon_vert,fragmentShader:Z.meshtoon_frag},matcap:{uniforms:St([V.common,V.bumpmap,V.normalmap,V.displacementmap,V.fog,{matcap:{value:null}}]),vertexShader:Z.meshmatcap_vert,fragmentShader:Z.meshmatcap_frag},points:{uniforms:St([V.points,V.fog]),vertexShader:Z.points_vert,fragmentShader:Z.points_frag},dashed:{uniforms:St([V.common,V.fog,{scale:{value:1},dashSize:{value:1},totalSize:{value:2}}]),vertexShader:Z.linedashed_vert,fragmentShader:Z.linedashed_frag},depth:{uniforms:St([V.common,V.displacementmap]),vertexShader:Z.depth_vert,fragmentShader:Z.depth_frag},normal:{uniforms:St([V.common,V.bumpmap,V.normalmap,V.displacementmap,{opacity:{value:1}}]),vertexShader:Z.meshnormal_vert,fragmentShader:Z.meshnormal_frag},sprite:{uniforms:St([V.sprite,V.fog]),vertexShader:Z.sprite_vert,fragmentShader:Z.sprite_frag},background:{uniforms:{uvTransform:{value:new Y},t2D:{value:null},backgroundIntensity:{value:1}},vertexShader:Z.background_vert,fragmentShader:Z.background_frag},backgroundCube:{uniforms:{envMap:{value:null},backgroundBlurriness:{value:0},backgroundIntensity:{value:1},backgroundRotation:{value:new Y}},vertexShader:Z.backgroundCube_vert,fragmentShader:Z.backgroundCube_frag},cube:{uniforms:{tCube:{value:null},tFlip:{value:-1},opacity:{value:1}},vertexShader:Z.cube_vert,fragmentShader:Z.cube_frag},equirect:{uniforms:{tEquirect:{value:null}},vertexShader:Z.equirect_vert,fragmentShader:Z.equirect_frag},distance:{uniforms:St([V.common,V.displacementmap,{referencePosition:{value:new k},nearDistance:{value:1},farDistance:{value:1e3}}]),vertexShader:Z.distance_vert,fragmentShader:Z.distance_frag},shadow:{uniforms:St([V.lights,V.fog,{color:{value:new gt(0)},opacity:{value:1}}]),vertexShader:Z.shadow_vert,fragmentShader:Z.shadow_frag}};Sr.physical={uniforms:St([Sr.standard.uniforms,{clearcoat:{value:0},clearcoatMap:{value:null},clearcoatMapTransform:{value:new Y},clearcoatNormalMap:{value:null},clearcoatNormalMapTransform:{value:new Y},clearcoatNormalScale:{value:new pt(1,1)},clearcoatRoughness:{value:0},clearcoatRoughnessMap:{value:null},clearcoatRoughnessMapTransform:{value:new Y},dispersion:{value:0},iridescence:{value:0},iridescenceMap:{value:null},iridescenceMapTransform:{value:new Y},iridescenceIOR:{value:1.3},iridescenceThicknessMinimum:{value:100},iridescenceThicknessMaximum:{value:400},iridescenceThicknessMap:{value:null},iridescenceThicknessMapTransform:{value:new Y},sheen:{value:0},sheenColor:{value:new gt(0)},sheenColorMap:{value:null},sheenColorMapTransform:{value:new Y},sheenRoughness:{value:1},sheenRoughnessMap:{value:null},sheenRoughnessMapTransform:{value:new Y},transmission:{value:0},transmissionMap:{value:null},transmissionMapTransform:{value:new Y},transmissionSamplerSize:{value:new pt},transmissionSamplerMap:{value:null},thickness:{value:0},thicknessMap:{value:null},thicknessMapTransform:{value:new Y},attenuationDistance:{value:0},attenuationColor:{value:new gt(0)},specularColor:{value:new gt(1,1,1)},specularColorMap:{value:null},specularColorMapTransform:{value:new Y},specularIntensity:{value:1},specularIntensityMap:{value:null},specularIntensityMapTransform:{value:new Y},anisotropyVector:{value:new pt},anisotropyMap:{value:null},anisotropyMapTransform:{value:new Y}}]),vertexShader:Z.meshphysical_vert,fragmentShader:Z.meshphysical_frag};var gh=new Y;gh.set(-1,0,0,0,1,0,0,0,1);var Gx={[Ki]:"LINEAR_TONE_MAPPING",[ji]:"REINHARD_TONE_MAPPING",[Qi]:"CINEON_TONE_MAPPING",[ts]:"ACES_FILMIC_TONE_MAPPING",[ns]:"AGX_TONE_MAPPING",[is]:"NEUTRAL_TONE_MAPPING",[es]:"CUSTOM_TONE_MAPPING"};var Hx=new Float32Array(16),Wx=new Float32Array(9),Xx=new Float32Array(4);var qx={[Ki]:"Linear",[ji]:"Reinhard",[Qi]:"Cineon",[ts]:"ACESFilmic",[ns]:"AgX",[is]:"Neutral",[es]:"Custom"};var $x={[nr]:"SHADOWMAP_TYPE_PCF",[ir]:"SHADOWMAP_TYPE_VSM"};var Yx={[ar]:"ENVMAP_TYPE_CUBE",[rs]:"ENVMAP_TYPE_CUBE",[cr]:"ENVMAP_TYPE_CUBE_UV"};var Zx={[rs]:"ENVMAP_MODE_REFRACTION"};var Jx={[sr]:"ENVMAP_BLENDING_MULTIPLY",[rr]:"ENVMAP_BLENDING_MIX",[or]:"ENVMAP_BLENDING_ADD"};var xh=new Y;xh.set(-1,0,0,0,1,0,0,0,1);var Kx=new Uint16Array([12469,15057,12620,14925,13266,14620,13807,14376,14323,13990,14545,13625,14713,13328,14840,12882,14931,12528,14996,12233,15039,11829,15066,11525,15080,11295,15085,10976,15082,10705,15073,10495,13880,14564,13898,14542,13977,14430,14158,14124,14393,13732,14556,13410,14702,12996,14814,12596,14891,12291,14937,11834,14957,11489,14958,11194,14943,10803,14921,10506,14893,10278,14858,9960,14484,14039,14487,14025,14499,13941,14524,13740,14574,13468,14654,13106,14743,12678,14818,12344,14867,11893,14889,11509,14893,11180,14881,10751,14852,10428,14812,10128,14765,9754,14712,9466,14764,13480,14764,13475,14766,13440,14766,13347,14769,13070,14786,12713,14816,12387,14844,11957,14860,11549,14868,11215,14855,10751,14825,10403,14782,10044,14729,9651,14666,9352,14599,9029,14967,12835,14966,12831,14963,12804,14954,12723,14936,12564,14917,12347,14900,11958,14886,11569,14878,11247,14859,10765,14828,10401,14784,10011,14727,9600,14660,9289,14586,8893,14508,8533,15111,12234,15110,12234,15104,12216,15092,12156,15067,12010,15028,11776,14981,11500,14942,11205,14902,10752,14861,10393,14812,9991,14752,9570,14682,9252,14603,8808,14519,8445,14431,8145,15209,11449,15208,11451,15202,11451,15190,11438,15163,11384,15117,11274,15055,10979,14994,10648,14932,10343,14871,9936,14803,9532,14729,9218,14645,8742,14556,8381,14461,8020,14365,7603,15273,10603,15272,10607,15267,10619,15256,10631,15231,10614,15182,10535,15118,10389,15042,10167,14963,9787,14883,9447,14800,9115,14710,8665,14615,8318,14514,7911,14411,7507,14279,7198,15314,9675,15313,9683,15309,9712,15298,9759,15277,9797,15229,9773,15166,9668,15084,9487,14995,9274,14898,8910,14800,8539,14697,8234,14590,7790,14479,7409,14367,7067,14178,6621,15337,8619,15337,8631,15333,8677,15325,8769,15305,8871,15264,8940,15202,8909,15119,8775,15022,8565,14916,8328,14804,8009,14688,7614,14569,7287,14448,6888,14321,6483,14088,6171,15350,7402,15350,7419,15347,7480,15340,7613,15322,7804,15287,7973,15229,8057,15148,8012,15046,7846,14933,7611,14810,7357,14682,7069,14552,6656,14421,6316,14251,5948,14007,5528,15356,5942,15356,5977,15353,6119,15348,6294,15332,6551,15302,6824,15249,7044,15171,7122,15070,7050,14949,6861,14818,6611,14679,6349,14538,6067,14398,5651,14189,5311,13935,4958,15359,4123,15359,4153,15356,4296,15353,4646,15338,5160,15311,5508,15263,5829,15188,6042,15088,6094,14966,6001,14826,5796,14678,5543,14527,5287,14377,4985,14133,4586,13869,4257,15360,1563,15360,1642,15358,2076,15354,2636,15341,3350,15317,4019,15273,4429,15203,4732,15105,4911,14981,4932,14836,4818,14679,4621,14517,4386,14359,4156,14083,3795,13808,3437,15360,122,15360,137,15358,285,15355,636,15344,1274,15322,2177,15281,2765,15215,3223,15120,3451,14995,3569,14846,3567,14681,3466,14511,3305,14344,3121,14037,2800,13753,2467,15360,0,15360,1,15359,21,15355,89,15346,253,15325,479,15287,796,15225,1148,15133,1492,15008,1749,14856,1882,14685,1886,14506,1783,14324,1608,13996,1398,13702,1183]);function ls(i,t,e,n){let s=e;if(n>=i[s])return s-1;if(n<=i[t])return t;let r=t,o=s,a=r+o>>1;for(;n<i[a]||n>=i[a+1];)n<i[a]?o=a:r=a,a=r+o>>1;return a}p(ls,"findSpan");var br=new Map;function mn(i,t){let e=br.get(t);e||br.set(t,e=[]);let n=e[i];return n||(e[i]=n=new Float64Array(t)),n}p(mn,"scratch");function hs(i,t,e,n,s){let r=mn(0,t+1),o=mn(1,t+1);s[0]=1;for(let a=1;a<=t;a+=1){r[a]=n-i[e+1-a],o[a]=i[e+a]-n;let c=0;for(let l=0;l<a;l+=1){let h=s[l]/(o[l+1]+r[a-l]);s[l]=c+o[l+1]*h,c=r[a-l]*h}s[a]=c}return s}p(hs,"basisFunctions");function Ar(i,t,e,n){let s=i.deg,r=jt(t,i.poles),o=jt(t,i.knots),a=i.weights?jt(t,i.weights):null;if(i.period){let[f,d]=i.range;(e>d||e<f)&&(e=f+((e-f)%i.period+i.period)%i.period)}let c=ls(o,s,i.n,e),l=hs(o,s,c,e,mn(2,s+1)),h=[0,0,0],u=0;for(let f=0;f<=s;f+=1){let d=c-s+f,m=a?a[d]:1,g=l[f]*m;for(let _=0;_<n;_+=1)h[_]+=g*r[d*n+_];u+=g}for(let f=0;f<n;f+=1)h[f]/=u;return h.slice(0,n)}p(Ar,"evaluateBSplineCurve");var _h={line(i,t){let{origin:e,dir:n}=i;return[e[0]+t*n[0],e[1]+t*n[1],e[2]+t*n[2]]},circle(i,t){let e=Math.cos(t)*i.radius,n=Math.sin(t)*i.radius;return _e(i,e,n,0)},ellipse(i,t){let e=Math.cos(t)*i.majorRadius,n=Math.sin(t)*i.minorRadius;return _e(i,e,n,0)}};function Xt(i,t,e){let n=_h[i.kind];if(n)return n(i,e);if(i.kind==="bspline")return Ar(i,t,e,3);throw new Error(`unknown curve kind ${i.kind}`)}p(Xt,"evaluateCurve3");function gn(i,t,e){return Ar(i,t,e,2)}p(gn,"evaluatePCurve");function _e(i,t,e,n){let{origin:s,xdir:r,ydir:o,zdir:a}=i;return[s[0]+t*r[0]+e*o[0]+n*a[0],s[1]+t*r[1]+e*o[1]+n*a[1],s[2]+t*r[2]+e*o[2]+n*a[2]]}p(_e,"frameMix");function yh(i,t,e,n){let{degU:s,degV:r,nu:o,nv:a}=i,c=jt(t,i.poles),l=jt(t,i.knotsU),h=jt(t,i.knotsV),u=i.weights?jt(t,i.weights):null,f=ls(l,s,o,e),d=ls(h,r,a,n),m=hs(l,s,f,e,mn(2,s+1)),g=hs(h,r,d,n,mn(3,r+1)),_=0,x=0,M=0,y=0;for(let v=0;v<=s;v+=1){let b=f-s+v;for(let A=0;A<=r;A+=1){let w=d-r+A,S=b*a+w,C=u?u[S]:1,T=m[v]*g[A]*C;_+=T*c[S*3],x+=T*c[S*3+1],M+=T*c[S*3+2],y+=T}}return[_/y,x/y,M/y]}p(yh,"evaluateNurbsSurface");var vh={plane(i,t,e){return _e(i,t,e,0)},cylinder(i,t,e){let n=i.radius;return _e(i,n*Math.cos(t),n*Math.sin(t),e)},cone(i,t,e){let n=i.radius+e*Math.sin(i.semiAngle);return _e(i,n*Math.cos(t),n*Math.sin(t),e*Math.cos(i.semiAngle))},sphere(i,t,e){let n=i.radius,s=Math.cos(e);return _e(i,n*s*Math.cos(t),n*s*Math.sin(t),n*Math.sin(e))},torus(i,t,e){let n=i.majorRadius+i.minorRadius*Math.cos(e);return _e(i,n*Math.cos(t),n*Math.sin(t),i.minorRadius*Math.sin(e))}};function ht(i,t,e,n){let s=vh[i.kind];if(s)return s(i,e,n);if(i.kind==="nurbs")return yh(i,t,e,n);if(i.kind==="revolution"){let r=Xt(i.profile,t,n);return Mh(r,i.origin,i.dir,e)}if(i.kind==="extrusion"){let r=Xt(i.profile,t,e);return[r[0]+n*i.dir[0],r[1]+n*i.dir[1],r[2]+n*i.dir[2]]}throw new Error(`unknown surface kind ${i.kind}`)}p(ht,"evaluateSurface");function Mh(i,t,e,n){let s=i[0]-t[0],r=i[1]-t[1],o=i[2]-t[2],[a,c,l]=e,h=Math.cos(n),u=Math.sin(n),f=a*s+c*r+l*o,d=c*o-l*r,m=l*s-a*o,g=a*r-c*s;return[t[0]+s*h+d*u+a*f*(1-h),t[1]+r*h+m*u+c*f*(1-h),t[2]+o*h+g*u+l*f*(1-h)]}p(Mh,"rotateAroundAxis");function ei(i,t,e,n,s,r){let[o,a,c,l]=s,h=Math.max((a-o)*1e-4,1e-7),u=Math.max((l-c)*1e-4,1e-7),f=ht(i,t,e-h,n),d=ht(i,t,e+h,n),m=ht(i,t,e,n-u),g=ht(i,t,e,n+u),_=[d[0]-f[0],d[1]-f[1],d[2]-f[2]],x=[g[0]-m[0],g[1]-m[1],g[2]-m[2]],M=_[1]*x[2]-_[2]*x[1],y=_[2]*x[0]-_[0]*x[2],v=_[0]*x[1]-_[1]*x[0],b=Math.hypot(M,y,v)||1,A=r?-1:1;return M=M/b*A,y=y/b*A,v=v/b*A,[M,y,v]}p(ei,"evaluateSurfaceNormal");var Cr=1,Bt={chordTolerance:.0015,loopTolerance:5e-4,angleTolerance:.35,maxRefineDepth:7,minLoopSegments:8};function et(i,t){return[i[0]-t[0],i[1]-t[1],i[2]-t[2]]}p(et,"sub");function ot(i){return Math.hypot(i[0],i[1],i[2])}p(ot,"length3");function wr(i,t,e,n,s){let r=[],o=[],a=[];for(let c of t){let l=!c.reversed,h=c.edgeOrd?s?.get(c.edgeOrd):null,u=null,f=null;if(h&&h.points.length>=2){let d=bh(i,c,e,n,h);d&&(u=d.uvs,f=d.fractions)}u||(u=Sh(i,c,e,n)),l||(u.reverse(),f?.reverse());for(let d=0;d<u.length-1;d+=1)r.push(u[d]),o.push(c.edgeOrd||0),a.push(f?{ord:c.edgeOrd,f0:f[d],f1:f[d+1]}:null)}return r.segmentOrds=o,r.segmentMeta=a,r}p(wr,"sampleLoopPolygon");function Rr(i,t,e,n){let[s,r]=t.range,o=i.surface,a=p(g=>gn(t,e,g),"uvOf"),c=p(g=>ht(o,e,g[0],g[1]),"xyzOf"),l=c(a(s)),h=c(a(r)),u=ot(et(l,h))<=n,f=Math.max(u?Bt.minLoopSegments:2,t.n??2),d=[];for(let g=0;g<=f;g+=1)d.push(s+(r-s)*g/f);let m=0;for(;m<Bt.maxRefineDepth;){let g=!1,_=[d[0]];for(let x=0;x+1<d.length;x+=1){let M=d[x],y=d[x+1],v=(M+y)/2,b=c(a(M)),A=c(a(y)),w=c(a(v)),S=[(b[0]+A[0])/2,(b[1]+A[1])/2,(b[2]+A[2])/2];ot(et(w,S))>n&&(_.push(v),g=!0),_.push(y)}if(d.length=0,d.push(..._),!g)break;m+=1}return{params:d,uvs:d.map(a)}}p(Rr,"samplePCurveParams");function Sh(i,t,e,n){return Rr(i,t,e,n).uvs}p(Sh,"samplePCurveAdaptive");function bh(i,t,e,n,s){let r=Rr(i,t,e,n);if(r.uvs.length<2)return null;let o=i.surface,a=r.uvs.map(b=>ht(o,e,b[0],b[1])),c=[0];for(let b=1;b<a.length;b+=1)c.push(c[b-1]+ot(et(a[b],a[b-1])));let l=c[c.length-1];if(!(l>0))return null;for(let b=0;b<c.length;b+=1)c[b]/=l;let h=s.points[0],u=s.points[s.points.length-1],f=ot(et(h,a[0]))+ot(et(u,a[a.length-1])),m=ot(et(h,a[a.length-1]))+ot(et(u,a[0]))<f,g=[],_=[],x=[],M=s.boundarySubset||s.points.map((b,A)=>A),y=M.length,v=0;for(let b=0;b<y;b+=1){let A=M[m?y-1-b:b],w=s.fractions[A],S=m?1-w:w;for(;v+1<c.length-1&&c[v+1]<S;)v+=1;let C;if(b===0)C=r.params[0];else if(b===y-1)C=r.params[r.params.length-1];else{let P=c[v],R=c[v+1],I=R>P?(S-P)/(R-P):0;C=r.params[v]+I*(r.params[v+1]-r.params[v])}let T=gn(t,e,C),D=s.points[A],L=ht(o,e,T[0],T[1]);if(ot(et(L,D))>n*2)return null;g.push(T),_.push(w),x.push(C)}if(o.kind!=="plane"){let b=g.map(A=>ht(o,e,A[0],A[1]));for(let A=0;A<4;A+=1){let w=!1,S=[g[0]],C=[_[0]],T=[x[0]],D=[b[0]];for(let L=0;L+1<g.length;L+=1){let P=b[L],R=b[L+1],I=(x[L]+x[L+1])/2,E=gn(t,e,I),F=ht(o,e,E[0],E[1]),O=[(P[0]+R[0])/2,(P[1]+R[1])/2,(P[2]+R[2])/2];ot(et(F,O))>n&&(S.push(E),C.push((_[L]+_[L+1])/2),T.push(I),D.push(F),w=!0),S.push(g[L+1]),C.push(_[L+1]),T.push(x[L+1]),D.push(b[L+1])}if(g.length=0,_.length=0,x.length=0,b.length=0,g.push(...S),_.push(...C),x.push(...T),b.push(...D),!w)break}}return{uvs:g,fractions:_}}p(bh,"mapSharedEdgeToPCurve");function us(i,t,e){let n=i.fractions,s=n.length-1;if(t<=n[0])return i.points[0];if(t>=n[s])return i.points[s];let r=0,o=s;for(;r+1<o;){let f=r+o>>1;n[f]<=t?r=f:o=f}let a=n[r],c=n[r+1];if(t===a)return i.points[r];if(t===c)return i.points[r+1];let l=c>a?(t-a)/(c-a):0;if(i.curve&&e){let f=i.params[r]+l*(i.params[r+1]-i.params[r]);return Xt(i.curve,e,f)}let h=i.points[r],u=i.points[r+1];return[h[0]+l*(u[0]-h[0]),h[1]+l*(u[1]-h[1]),h[2]+l*(u[2]-h[2])]}p(us,"edgePointAt");function Ah(i,t,e){let[n,s]=i.range,r=Xt(i,t,n),o=Xt(i,t,s),a=ot(et(r,o))<=e,c=i.kind==="line"?1:Math.max(a?8:4,i.n??2),l=[];for(let g=0;g<=c;g+=1)l.push(n+(s-n)*g/c);let h=0;for(;h<Bt.maxRefineDepth;){let g=!1,_=[l[0]];for(let x=0;x+1<l.length;x+=1){let M=l[x],y=l[x+1],v=(M+y)/2,b=Xt(i,t,M),A=Xt(i,t,y),w=Xt(i,t,v),S=[(b[0]+A[0])/2,(b[1]+A[1])/2,(b[2]+A[2])/2];ot(et(w,S))>e&&(_.push(v),g=!0),_.push(y)}if(l.length=0,l.push(..._),!g)break;h+=1}let u=l.map(g=>Xt(i,t,g));a&&u.length>1&&(u[u.length-1]=u[0]);let f=[0];for(let g=1;g<u.length;g+=1)f.push(f[g-1]+ot(et(u[g],u[g-1])));let d=f[f.length-1];if(d>0){for(let g=0;g<f.length;g+=1)f[g]/=d;f[f.length-1]=1}let m=[0];{let g=e*(Bt.loopTolerance/Bt.chordTolerance),_=0;for(let x=1;x<u.length;x+=1){if(x===u.length-1){m.push(x);break}let M=u[_],y=u[x+1],v=0;for(let b=_+1;b<=x;b+=1){let A=et(u[b],M),w=et(y,M),S=w[0]*w[0]+w[1]*w[1]+w[2]*w[2],C=S>0?(A[0]*w[0]+A[1]*w[1]+A[2]*w[2])/S:0,T=Math.max(0,Math.min(1,C)),D=[M[0]+T*w[0],M[1]+T*w[1],M[2]+T*w[2]];if(v=Math.max(v,ot(et(u[b],D))),v>g)break}v>g&&(m.push(x),_=x)}}return{curve:i,params:l,points:u,fractions:f,closed:a,length:d,boundarySubset:m}}p(Ah,"sampleSharedEdge");function wh(i){let t=0;for(let e=0;e<i.length;e+=1){let[n,s]=i[e],[r,o]=i[(e+1)%i.length];t+=n*o-r*s}return t/2}p(wh,"polygonArea");function Tr(i,t,e,n,s){let[r,o,a,c]=e,l=s===0?o-r:c-a;if(l<=0)return 1;let h=4,u=0;for(let d=0;d<=h;d+=1){let m=s===0?a+(c-a)*d/h:r+(o-r)*d/h;for(let g=0;g<h;g+=1){let _=(s===0?r:a)+l*g/h,x=_+l/h,M=(_+x)/2,y=p(S=>s===0?ht(i.surface,t,S,m):ht(i.surface,t,m,S),"at"),v=y(_),b=y(x),A=y(M),w=[(v[0]+b[0])/2,(v[1]+b[1])/2,(v[2]+b[2])/2];u=Math.max(u,ot(et(A,w)))}}if(u<=n)return 1;let f=Math.sqrt(u/n);return Math.min(256,Math.max(1,Math.ceil(h*f)))}p(Tr,"gridStepsForDirection");function Th(i,t,e){let n=!1;for(let s of i)for(let r=0;r<s.length;r+=1){let[o,a]=s[r],[c,l]=s[(r+1)%s.length];a>e!=l>e&&t<(c-o)*(e-a)/(l-a)+o&&(n=!n)}return n}p(Th,"pointInLoopsEvenOdd");function Eh(i,t,e,n,s){let r=i;for(let[o,a,c]of[[0,t,!1],[0,e,!0],[1,n,!1],[1,s,!0]]){let l=r;r=[];for(let h=0;h<l.length;h+=1){let u=l[h],f=l[(h+l.length-1)%l.length],d=c?u[o]<=a:u[o]>=a,m=c?f[o]<=a:f[o]>=a;if(d!==m){let g=(a-f[o])/(u[o]-f[o]);r.push([f[0]+g*(u[0]-f[0]),f[1]+g*(u[1]-f[1])])}d&&r.push(u)}if(r.length<3)return[]}return r}p(Eh,"clipPolygonToCell");function Ch(i,t,e,n){let s=1/0,r=-1/0,o=1/0,a=-1/0;for(let S of e)for(let[C,T]of S)C<s&&(s=C),C>r&&(r=C),T<o&&(o=T),T>a&&(a=T);if(!(r>s)||!(a>o))return null;let c=[s,r,o,a],l=Tr(i,t,c,n,0),h=Tr(i,t,c,n,1),u=(r-s)/l,f=(a-o)/h,d=p((S,C)=>[Math.min(l-1,Math.max(0,Math.floor((S-s)/u))),Math.min(h-1,Math.max(0,Math.floor((C-o)/f)))],"cellOf"),m=new Set,g=[],_=new Map;for(let S of e){let C=S.segmentOrds||[],T=S.segmentMeta||[];for(let D=0;D<S.length;D+=1){let[L,P]=S[D],[R,I]=S[(D+1)%S.length],E=g.length;g.push([L,P,R,I,C[D]||0,T[D]||null]);let[F,O]=d(Math.min(L,R),Math.min(P,I)),[N,U]=d(Math.max(L,R),Math.max(P,I));for(let z=F;z<=N;z+=1)for(let B=O;B<=U;B+=1){let H=z*h+B;m.add(H);let W=_.get(H);W||_.set(H,W=[]),W.push(E)}}}let x=[],M=new Map,y=p((S,C)=>{let T=`${S}:${C}`,D=M.get(T);return D===void 0&&(D=x.length,x.push([S,C]),M.set(T,D)),D},"vertexId"),v=[],b=Math.abs((r-s)*(a-o))*1e-12||1e-30,A=[],w=[];for(let S=0;S<=l;S+=1)A.push(S===l?r:s+S*u);for(let S=0;S<=h;S+=1)w.push(S===h?a:o+S*f);for(let S=0;S<l;S+=1)for(let C=0;C<h;C+=1){let T=A[S],D=A[S+1],L=w[C],P=w[C+1];if(!m.has(S*h+C)){if(!Th(e,(T+D)/2,(L+P)/2))continue;let B=y(T,L),H=y(D,L),W=y(D,P),G=y(T,P);v.push(B,H,W,B,W,G);continue}let R=e.map(B=>Eh(B,T,D,L,P)).filter(B=>B.length>=3);if(!R.length)continue;let I=0,E=0;for(let B=0;B<R.length;B+=1){let H=Math.abs(wh(R[B]));H>E&&(E=H,I=B)}if(E<=b)continue;let F=R[I].map(([B,H])=>new pt(B,H)),O=R.filter((B,H)=>H!==I).map(B=>B.map(([H,W])=>new pt(H,W))),N;try{N=dn.triangulateShape(F,O)}catch{continue}let U=[...F,...O.flat()],z=U.map(({x:B,y:H})=>y(B,H));for(let[B,H,W]of N){let G=U[B],X=U[H],q=U[W],$=(X.x-G.x)*(q.y-G.y)-(q.x-G.x)*(X.y-G.y);Math.abs($)/2>b&&v.push(z[B],z[H],z[W])}}return{uvVerts:x,triangles:v,vertexIds:M,segmentIndex:{segments:g,segmentsByCell:_,cellOf:d,stepsV:h}}}p(Ch,"gridTriangulate");function Rh(i,t,e,n,s,r){let o=s-e,a=r-n,c=o*o+a*a,l=c>0?((i-e)*o+(t-n)*a)/c:0;l=Math.max(0,Math.min(1,l));let h=e+l*o,u=n+l*a;return{distSq:(i-h)*(i-h)+(t-u)*(t-u),t:l}}p(Rh,"projectToSegment");function Er(i,t,e,n,s,r){let o=s-e,a=r-n,c=o*o+a*a,l=c>0?((i-e)*o+(t-n)*a)/c:0;l=Math.max(0,Math.min(1,l));let h=e+l*o,u=n+l*a;return(i-h)*(i-h)+(t-u)*(t-u)}p(Er,"pointToSegmentDistanceSq");function Ih(i,t,e,n){let s=new Map,r=p((m,g)=>m<g?m*4294967296+g:g*4294967296+m,"keyOf");for(let m=0;m<i.length;m+=3){let[g,_,x]=[i[m],i[m+1],i[m+2]];for(let[M,y]of[[g,_],[_,x],[x,g]]){let v=r(M,y);s.set(v,(s.get(v)||0)+1)}}let{segments:o,segmentsByCell:a,cellOf:c,stepsV:l}=e,h=n*n,u=new Map,f=p((m,g)=>{let _=r(m,g);if(s.get(_)!==1)return 0;let x=u.get(_);if(x!==void 0)return x;x=0;let[M,y]=t[m],[v,b]=t[g],[A,w]=c((M+v)/2,(y+b)/2),S=a.get(A*l+w)||[];for(let C of S){let[T,D,L,P,R]=o[C];if(R&&Er(M,y,T,D,L,P)<h&&Er(v,b,T,D,L,P)<h){x=R;break}}return u.set(_,x),x},"ordOfMeshEdge"),d=new Uint32Array(i.length);for(let m=0;m<i.length;m+=3){let[g,_,x]=[i[m],i[m+1],i[m+2]];d[m]=f(_,x),d[m+1]=f(x,g),d[m+2]=f(g,_)}return d}p(Ih,"attributeBoundaryEdges");function Ph(i,t,e,n={},s=null){let{chordTolerance:r,loopTolerance:o,angleTolerance:a,maxRefineDepth:c}={...Bt,...n},l=o*e,h=i.loops.map(L=>wr(i,L,t,l,s)).filter(L=>L.length>=3);if(!h.length)return null;let u=0;{let L=1/0,P=-1/0,R=1/0,I=-1/0;for(let F of h)for(let[O,N]of F)O<L&&(L=O),O>P&&(P=O),N<R&&(R=N),N>I&&(I=N);let E=[[L,R],[P,R],[L,I],[P,I],[(L+P)/2,(R+I)/2]].map(([F,O])=>ht(i.surface,t,F,O));for(let F=0;F<E.length;F+=1)for(let O=F+1;O<E.length;O+=1)u=Math.max(u,ot(et(E[F],E[O])))}let f=Math.max(Math.min(e,u*4),1e-9),d=r*f,m=o*f,g=m<l?i.loops.map(L=>wr(i,L,t,m,s)).filter(L=>L.length>=3):h;if(!g.length)return null;let _=Ch(i,t,g,d);if(!_)return null;let{uvVerts:x,triangles:M,vertexIds:y,segmentIndex:v}=_,b=M;if(!b.length)return null;let A=x.map(([L,P])=>ht(i.surface,t,L,P)),w=p(([L,P])=>ei(i.surface,t,L,P,i.uv,!1),"vertexNormal"),S=x.map(w),C=Math.cos(a),T=p((L,P)=>L<P?`${L}_${P}`:`${P}_${L}`,"edgeKey");for(let L=0;L<c;L+=1){let P=new Set,R=new Map,I=p((N,U)=>{let z=T(N,U),B=R.get(z);if(B===void 0){let H=(x[N][0]+x[U][0])/2,W=(x[N][1]+x[U][1])/2,G=ht(i.surface,t,H,W),X=[(A[N][0]+A[U][0])/2,(A[N][1]+A[U][1])/2,(A[N][2]+A[U][2])/2];B=ot(et(G,X))>d||S[N][0]*S[U][0]+S[N][1]*S[U][1]+S[N][2]*S[U][2]<C,R.set(z,B)}return B},"edgeChordBad");for(let N=0;N<b.length;N+=3){let U=b[N],z=b[N+1],B=b[N+2],H=!1;for(let[xt,yt]of[[U,z],[z,B],[B,U]])I(xt,yt)&&(P.add(T(xt,yt)),H=!0);if(H)continue;let W=(x[U][0]+x[z][0]+x[B][0])/3,G=(x[U][1]+x[z][1]+x[B][1])/3,X=ht(i.surface,t,W,G),q=[(A[U][0]+A[z][0]+A[B][0])/3,(A[U][1]+A[z][1]+A[B][1])/3,(A[U][2]+A[z][2]+A[B][2])/3],$=et(A[z],A[U]),K=et(A[B],A[U]),Q=[$[1]*K[2]-$[2]*K[1],$[2]*K[0]-$[0]*K[2],$[0]*K[1]-$[1]*K[0]],j=ot(Q),ct=S[U];if(j>1e-30&&Math.abs((Q[0]*ct[0]+Q[1]*ct[1]+Q[2]*ct[2])/j)<C||ot(et(X,q))>d){let xt=[U,z],yt=-1;for(let[Wt,he]of[[U,z],[z,B],[B,U]]){let At=x[Wt][0]-x[he][0],ue=x[Wt][1]-x[he][1],kt=At*At+ue*ue;kt>yt&&(yt=kt,xt=[Wt,he])}P.add(T(xt[0],xt[1]))}}if(!P.size)break;let E=new Map,F=p((N,U)=>{let z=T(N,U);if(!P.has(z))return-1;let B=E.get(z);if(B===void 0){let H=(x[N][0]+x[U][0])/2,W=(x[N][1]+x[U][1])/2;B=x.length,x.push([H,W]),A.push(ht(i.surface,t,H,W)),S.push(w([H,W])),E.set(z,B)}return B},"midpointOf"),O=[];for(let N=0;N<b.length;N+=3){let U=b[N],z=b[N+1],B=b[N+2],H=F(U,z),W=F(z,B),G=F(B,U),X=(H>=0)+(W>=0)+(G>=0);if(X===0){O.push(U,z,B);continue}if(X===3)O.push(U,H,G,H,z,W,G,W,B,H,W,G);else if(X===2){let[q,$,K,Q,j]=H>=0&&W>=0?[U,z,B,H,W]:W>=0&&G>=0?[z,B,U,W,G]:[B,U,z,G,H];O.push(q,Q,j,q,j,K,Q,$,j)}else{let[q,$,K,Q]=H>=0?[U,z,B,H]:W>=0?[z,B,U,W]:[B,U,z,G];O.push(q,Q,K,Q,$,K)}}b=O}let D=new Map;if(s){let L=0,P=0;for(let[N,U]of x)L=Math.max(L,Math.abs(N)),P=Math.max(P,Math.abs(U));let R=Math.max(L,P,1)*1e-7,{segments:I,segmentsByCell:E,cellOf:F,stepsV:O}=v;for(let N=0;N<x.length;N+=1){let[U,z]=x[N],[B,H]=F(U,z),W=E.get(B*O+H);if(!W)continue;let G=new Map;for(let $ of W){let[K,Q,j,ct,qt,xt]=I[$];if(!xt)continue;let yt=Rh(U,z,K,Q,j,ct);if(yt.distSq>=R*R){let At=R*R*16,ue=(U-K)*(U-K)+(z-Q)*(z-Q),kt=(U-j)*(U-j)+(z-ct)*(z-ct);if(ue<At)yt={distSq:ue,t:0};else if(kt<At)yt={distSq:kt,t:1};else continue}let Wt=G.get(qt);if(Wt&&Wt.distSq<=yt.distSq)continue;let he=yt.t<1e-9?0:yt.t>1-1e-9?1:yt.t;G.set(qt,{distSq:yt.distSq,f:xt.f0+he*(xt.f1-xt.f0)})}if(!G.size)continue;let X=[],q=null;for(let[$,{distSq:K,f:Q}]of G){let j=s.get($);if(!j)continue;let ct=j.closed&&Q>=1-1e-12?0:Q;X.push({ord:$,f:ct}),(!q||K<q.distSq)&&(q={distSq:K,ord:$,f:ct,shared:j})}X.length&&(X.sort(($,K)=>$.ord===q.ord&&$.f===q.f?-1:K.ord===q.ord&&K.f===q.f?1:0),D.set(N,X),A[N]=us(q.shared,q.f,t))}}return{uvVerts:x,xyz:A,nrm:S,triangles:b,segmentIndex:v,boundary:D}}p(Ph,"tessellateFaceRaw");function Lh(i,t,e,n={}){let{chordTolerance:s,angleTolerance:r,maxRefineDepth:o}={...Bt,...n},{uvVerts:a,xyz:c,nrm:l,boundary:h}=t,u=t.mintedVerts;if(!u?.size)return;let f=t.triangles,d=0;for(let y of c)d=Math.max(d,ot(et(y,c[0])));let m=s*Math.max(d,1e-9),g=p(([y,v])=>ei(i.surface,e,y,v,i.uv,!1),"vertexNormal"),_=Math.cos(r),x=p((y,v)=>y<v?`${y}_${v}`:`${v}_${y}`,"edgeKey"),M=Math.min(3,o);for(let y=0;y<M;y+=1){let v=new Set;for(let S=0;S<f.length;S+=3){let[C,T,D]=[f[S],f[S+1],f[S+2]];if(!(!u.has(C)&&!u.has(T)&&!u.has(D)))for(let[L,P]of[[C,T],[T,D],[D,C]]){if(h.has(L)&&h.has(P))continue;let R=(a[L][0]+a[P][0])/2,I=(a[L][1]+a[P][1])/2,E=ht(i.surface,e,R,I);if(!E||!Number.isFinite(E[0]))continue;let F=[(c[L][0]+c[P][0])/2,(c[L][1]+c[P][1])/2,(c[L][2]+c[P][2])/2];ot(et(E,F))>m&&v.add(x(L,P))}}if(!v.size)break;let b=new Map,A=p((S,C)=>{let T=x(S,C);if(!v.has(T))return-1;let D=b.get(T);if(D===void 0){let L=(a[S][0]+a[C][0])/2,P=(a[S][1]+a[C][1])/2;D=a.length,a.push([L,P]),c.push(ht(i.surface,e,L,P)),l.push(g([L,P])),b.set(T,D)}return D},"midpointOf"),w=[];for(let S=0;S<f.length;S+=3){let C=f[S],T=f[S+1],D=f[S+2],L=A(C,T),P=A(T,D),R=A(D,C),I=(L>=0)+(P>=0)+(R>=0);if(I===0)w.push(C,T,D);else if(I===3)w.push(C,L,R,L,T,P,R,P,D,L,P,R);else if(I===2){let[E,F,O,N,U]=L>=0&&P>=0?[C,T,D,L,P]:P>=0&&R>=0?[T,D,C,P,R]:[D,C,T,R,L];w.push(E,N,U,E,U,O,N,F,U)}else{let[E,F,O,N]=L>=0?[C,T,D,L]:P>=0?[T,D,C,P]:[D,C,T,R];w.push(E,N,O,N,F,O)}}f=w}t.triangles=f}p(Lh,"refineInteriorPostConform");function Nh(i,t){let{uvVerts:e,xyz:n,nrm:s,triangles:r,segmentIndex:o}=t,a=new Float32Array(n.length*3),c=new Float32Array(n.length*3),l=i.reversed?-1:1;for(let m=0;m<n.length;m+=1)a.set(n[m],m*3),c[m*3]=s[m][0]*l,c[m*3+1]=s[m][1]*l,c[m*3+2]=s[m][2]*l;let h=i.reversed?Uh(r):Uint32Array.from(r),u=0,f=0;for(let[m,g]of e)u=Math.max(u,Math.abs(m)),f=Math.max(f,Math.abs(g));let d=Ih(h,e,o,Math.max(u,f,1)*1e-7);return{positions:a,normals:c,indices:h,sideOrds:d,uv:e}}p(Nh,"finalizeFaceMesh");function Dh(i,t,e,n=0){let s=p(h=>{let u=t.get(h),f=u?.length?n*.5/u.length:0;return Math.max(1e-9,f)},"fractionEps"),r=1e-9,o=p((h,u)=>t.get(h)?.closed&&u>=1-Math.max(1e-6,s(h))?0:u,"canonicalFraction"),a=new Map,c=p((h,u)=>{let f=a.get(h);f||a.set(h,f=[]),f.push(o(h,u))},"addFraction");for(let{raw:h}of i)for(let u of h.boundary.values())for(let{ord:f,f:d}of u)c(f,d);for(let[h,u]of a){let f=s(h);u.sort((g,_)=>g-_);let d=[];for(let g of u)(!d.length||g-d[d.length-1]>f)&&d.push(g);t.get(h)?.closed&&d.length>1&&1-d[d.length-1]<=f&&d.pop(),a.set(h,d)}let l=p((h,u)=>{let f=a.get(h);if(!f)return u;let d=0,m=f.length-1;for(;d<m;){let _=d+m>>1;f[_]<u?d=_+1:m=_}let g=[f[d],f[d-1]??f[d]];return Math.abs(g[0]-u)<=Math.abs(g[1]-u)?g[0]:g[1]},"representativeOf");for(let{raw:h}of i){for(let[_,x]of h.boundary){for(let v of x)v.f=l(v.ord,o(v.ord,v.f));x.sort((v,b)=>v.ord-b.ord||v.f-b.f);let M=x[0],y=t.get(M.ord);y&&(h.xyz[_]=us(y,M.f,e))}let u=0;for(let[_,x]of h.uvVerts)u=Math.max(u,Math.abs(_),Math.abs(x));let f=Math.max(u,1)*.01,d=p((_,x)=>Math.abs(h.uvVerts[_][0]-h.uvVerts[x][0])<=f&&Math.abs(h.uvVerts[_][1]-h.uvVerts[x][1])<=f,"uvClose"),m=new Map,g=new Map;for(let _ of h.boundary.keys()){let x=h.xyz[_],M=`${x[0]}:${x[1]}:${x[2]}`,y=m.get(M);if(y===void 0){m.set(M,[_]);continue}let v=y.find(b=>d(b,_));v!==void 0?g.set(_,v):y.push(_)}if(g.size){let _=[];for(let x=0;x<h.triangles.length;x+=3){let M=g.get(h.triangles[x])??h.triangles[x],y=g.get(h.triangles[x+1])??h.triangles[x+1],v=g.get(h.triangles[x+2])??h.triangles[x+2];M!==y&&y!==v&&v!==M&&_.push(M,y,v)}h.triangles=_;for(let x of g.keys())h.boundary.delete(x)}}for(let{face:h,raw:u}of i){let{uvVerts:f,xyz:d,nrm:m,boundary:g}=u;if(!g.size)continue;let _=new Map,x=p((R,I)=>R<I?R*4294967296+I:I*4294967296+R,"pairKey");for(let R=0;R<u.triangles.length;R+=3){let[I,E,F]=[u.triangles[R],u.triangles[R+1],u.triangles[R+2]];for(let[O,N]of[[I,E],[E,F],[F,I]]){let U=x(O,N);_.set(U,(_.get(U)||0)+1)}}let M=p(([R,I])=>ei(h.surface,e,R,I,h.uv,!1),"vertexNormal"),y=new Map,v=p((R,I,E,F,O)=>{let N=`${R}:${I.toFixed(12)}:${Math.min(E,F)}:${Math.max(E,F)}`,U=y.get(N);if(U!==void 0)return U;let z=[f[E][0]+O*(f[F][0]-f[E][0]),f[E][1]+O*(f[F][1]-f[E][1])];U=f.length,f.push(z);let B=us(t.get(R),I,e);return d.push(B),m.push(M(z)),g.set(U,[{ord:R,f:I}]),(u.mintedVerts??=new Set).add(U),y.set(N,U),U},"vertexAt"),b=p((R,I)=>{let E=g.get(R),F=g.get(I);if(!E||!F||_.get(x(R,I))!==1)return null;let O=null,N=null;for(let W of E){let G=F.find(X=>X.ord===W.ord);if(G){O=W,N=G;break}}if(!O||!N)return null;let U=a.get(O.ord);if(!U)return null;let z=t.get(O.ord),B=s(O.ord),H=[];if(z?.closed){let W=(N.f-O.f+1)%1,G=W<=.5,X=G?O.f:N.f,q=G?W:(O.f-N.f+1)%1;if(q<=B*2)return null;for(let $ of U){let K=($-X+1)%1;K>B&&K<q-B&&H.push({f:$,s:G?K/q:1-K/q})}}else{let W=Math.min(O.f,N.f),G=Math.max(O.f,N.f);if(G-W<=B*2)return null;for(let X of U)X>W+B&&X<G-B&&H.push({f:X,s:(X-O.f)/(N.f-O.f)})}return H.length?(H.sort((W,G)=>W.s-G.s),{ord:O.ord,between:H}):null},"insertsFor"),A=[],w=p((R,I,E,F)=>{if(F>24){A.push(R,I,E);return}for(let[O,N,U]of[[R,I,E],[I,E,R],[E,R,I]]){let z=b(O,N);if(z){let B=O;for(let{f:H,s:W}of z.between){let G=v(z.ord,H,O,N,W);w(B,G,U,F+1),B=G}w(B,N,U,F+1);return}}A.push(R,I,E)},"emit"),S=u.triangles;for(let R=0;R<S.length;R+=3)w(S[R],S[R+1],S[R+2],0);u.triangles=A;let C=0;for(let[R,I]of f)C=Math.max(C,Math.abs(R),Math.abs(I));let T=Math.max(C,1)*.01,D=p((R,I)=>Math.abs(f[R][0]-f[I][0])<=T&&Math.abs(f[R][1]-f[I][1])<=T,"uvCloseAfter"),L=new Map,P=new Map;for(let R of g.keys()){let I=d[R],E=`${I[0]}:${I[1]}:${I[2]}`,F=L.get(E);if(F===void 0){L.set(E,[R]);continue}let O=F.find(N=>D(N,R));O!==void 0?P.set(R,O):F.push(R)}if(P.size){let R=[];for(let I=0;I<u.triangles.length;I+=3){let E=P.get(u.triangles[I])??u.triangles[I],F=P.get(u.triangles[I+1])??u.triangles[I+1],O=P.get(u.triangles[I+2])??u.triangles[I+2];E!==F&&F!==O&&O!==E&&R.push(E,F,O)}u.triangles=R;for(let[I,E]of P){let F=g.get(I),O=g.get(E);if(F&&O)for(let N of F)O.some(U=>U.ord===N.ord&&U.f===N.f)||O.push(N);g.delete(I)}}}}p(Dh,"conformBoundaries");function Uh(i){let t=new Uint32Array(i.length);for(let e=0;e<i.length;e+=3)t[e]=i[e],t[e+1]=i[e+2],t[e+2]=i[e+1];return t}p(Uh,"flipWinding");function fs(i,t,e={}){let n=[1/0,1/0,1/0],s=[-1/0,-1/0,-1/0],r=[],o=0,a=0;for(let A of i.faces)for(let w of A.loops)for(let S of w)for(let C of[S.range[0],(S.range[0]+S.range[1])/2,S.range[1]]){let[T,D]=gn(S,t,C),L=ht(A.surface,t,T,D);for(let P=0;P<3;P+=1)L[P]<n[P]&&(n[P]=L[P]),L[P]>s[P]&&(s[P]=L[P])}let c=Math.max(ot(et(s,n)),1e-6),{chordTolerance:l}={...Bt,...e},h=new Map;for(let A of i.edges)A.curve&&h.set(A.ord,Ah(A.curve,t,l*c));{let A=l*c,w=[],S=p(C=>{for(let T of w)if(ot(et(T,C))<=A)return T;return w.push(C),C},"canonicalCorner");for(let C of h.values()){if(C.closed){let T=S(C.points[0]);C.points[0]=T,C.points[C.points.length-1]=T;continue}C.points[0]=S(C.points[0]),C.points[C.points.length-1]=S(C.points[C.points.length-1])}}let u=[];for(let A of i.faces){let w=Ph(A,t,c,e,e.noSharedBoundaries?null:h);w&&u.push({face:A,raw:w})}if(!e.noSharedBoundaries&&!e.noConformPass){Dh(u,h,t,l*c);for(let{face:A,raw:w}of u)Lh(A,w,t,e)}let f=e.collectBoundaryDebug?[]:null;for(let{face:A,raw:w}of u){f&&f.push({faceOrd:A.ord,reversed:!!A.reversed,xyz:w.xyz,triangles:w.triangles.slice(),boundaryByVert:new Map(w.boundary)});let S=Nh(A,w);S&&(r.push({ord:A.ord,color:A.color??null,mesh:S}),o+=S.positions.length/3,a+=S.indices.length)}let d=new Float32Array(o*3),m=new Float32Array(o*3),g=new Float32Array(o),_=new Uint32Array(a),x=new Uint32Array(a),M=[],y=0,v=0;for(let{ord:A,color:w,mesh:S}of r){d.set(S.positions,y*3),m.set(S.normals,y*3),g.fill(A,y,y+S.positions.length/3);for(let C=0;C<S.indices.length;C+=1)_[v+C]=S.indices[C]+y;S.sideOrds&&x.set(S.sideOrds,v),M.push({ord:A,color:w,indexStart:v,indexCount:S.indices.length}),y+=S.positions.length/3,v+=S.indices.length}n=[1/0,1/0,1/0],s=[-1/0,-1/0,-1/0];for(let A=0;A<d.length;A+=3)for(let w=0;w<3;w+=1){let S=d[A+w];S<n[w]&&(n[w]=S),S>s[w]&&(s[w]=S)}let b=[];for(let A of i.edges){let w=h.get(A.ord);if(!w)continue;let S=new Float32Array(w.points.length*3);for(let C=0;C<w.points.length;C+=1)S.set(w.points[C],C*3);b.push({ord:A.ord,visibilityClass:A.class,polyline:S})}return{positions:d,normals:m,faceOrds:g,indices:_,sideOrds:x,faceRanges:M,edges:b,bounds:{min:n,max:s},scale:c,...f?{boundaryDebug:f,sharedEdges:h}:{}}}p(fs,"tessellateComponent");var Ir=1397966164,Pr=3;function Lr(i,t={}){let e={...Bt,...t},n=p(s=>Number(s).toExponential(6),"num");return`${i}-t${Cr}-l${n(e.chordTolerance)}-a${n(e.angleTolerance)}`}p(Lr,"tessellationCacheKey");function Fh(i){return i+3&-4}p(Fh,"align4");function Nr(i){return(Array.isArray(i?.edges)?i.edges:[]).map(e=>[e.ord,String(e.class??"none")])}p(Nr,"edgeClassesFromSurfIndex");function Dr(i,{partColor:t=null,edgeClasses:e=null}={}){let n=Array.isArray(i.edges)?i.edges:[],s=JSON.stringify({partColor:t??null,edgeClasses:Array.isArray(e)?e:null,faceRanges:i.faceRanges,bounds:{min:[...i.bounds.min],max:[...i.bounds.max]},scale:i.scale,positionCount:i.positions.length,normalCount:i.normals.length,faceOrdCount:i.faceOrds.length,indexCount:i.indices.length,sideOrdCount:i.sideOrds.length,edges:n.map(f=>({ord:f.ord,visibilityClass:f.visibilityClass??null,count:f.polyline.length}))}),r=new TextEncoder().encode(s),o=Fh(r.length),a=i.positions.length+i.normals.length+i.faceOrds.length+i.indices.length+i.sideOrds.length+n.reduce((f,d)=>f+d.polyline.length,0),c=new Uint8Array(12+o+a*4),l=new DataView(c.buffer);l.setUint32(0,Ir,!0),l.setUint32(4,Pr,!0),l.setUint32(8,o,!0),c.set(r,12),c.fill(32,12+r.length,12+o);let h=12+o,u=p((f,d)=>{new d(c.buffer,h,f.length).set(f),h+=f.length*4},"append");u(i.positions,Float32Array),u(i.normals,Float32Array),u(i.faceOrds,Float32Array),u(i.indices,Uint32Array),u(i.sideOrds,Uint32Array);for(let f of n)u(f.polyline,Float32Array);return c}p(Dr,"encodeComponentTessellation");function Ur(i){try{if(!(i instanceof Uint8Array)||i.length<12)return null;let t=new DataView(i.buffer,i.byteOffset,i.byteLength);if(t.getUint32(0,!0)!==Ir||t.getUint32(4,!0)!==Pr)return null;let e=t.getUint32(8,!0),n=JSON.parse(new TextDecoder().decode(i.subarray(12,12+e))),s=i.byteOffset+12+e,r=(n.positionCount+n.normalCount+n.faceOrdCount+n.indexCount+n.sideOrdCount+n.edges.reduce((m,g)=>m+g.count,0))*4;if(i.byteOffset+i.byteLength-s!==r)return null;let o=s%4===0,a=p((m,g)=>{let _=o?new g(i.buffer,s,m):new g(i.buffer.slice(s,s+m*4));return s+=m*4,_},"take"),c=a(n.positionCount,Float32Array),l=a(n.normalCount,Float32Array),h=a(n.faceOrdCount,Float32Array),u=a(n.indexCount,Uint32Array),f=a(n.sideOrdCount,Uint32Array),d=n.edges.map(m=>({ord:m.ord,visibilityClass:m.visibilityClass,polyline:a(m.count,Float32Array)}));return{component:{positions:c,normals:l,faceOrds:h,indices:u,sideOrds:f,faceRanges:n.faceRanges,edges:d,bounds:n.bounds,scale:n.scale},partColor:n.partColor??null,edgeClasses:Array.isArray(n.edgeClasses)?n.edgeClasses:null}}catch{return null}}p(Ur,"decodeComponentTessellation");var l_=64*1024*1024;import ni from"node:fs";import Oh from"node:os";import Ve from"node:path";function Fr(i=process.env){return i.CADGEN_MESH_CACHE!=="0"}p(Fr,"tessellationCacheEnabled");function Bh(i=process.env){let t=(i.CADGEN_CACHE_DIR||"").trim();if(t)return t;if(process.platform==="win32"){let e=(i.LOCALAPPDATA||"").trim();if(e)return Ve.join(e,"cadgen")}else{let e=(i.XDG_CACHE_HOME||"").trim();if(e)return Ve.join(e,"cadgen")}return Ve.join(Oh.homedir(),".cache","cadgen")}p(Bh,"cadgenCacheRootDir");function Or(){return Ve.join(Bh(),"meshes")}p(Or,"tessellationCacheDir");function Br(i){if(!Fr())return null;try{let t=ni.readFileSync(Ve.join(Or(),`${i}.tess`));return new Uint8Array(t.buffer,t.byteOffset,t.byteLength)}catch{return null}}p(Br,"readCachedTessellationBytes");function zr(i,t){if(Fr())try{let e=Or();ni.mkdirSync(e,{recursive:!0});let n=Ve.join(e,`${i}.tess`),s=`${n}.${process.pid}.tmp`;ni.writeFileSync(s,t),ni.renameSync(s,n)}catch{}}p(zr,"writeCachedTessellationBytes");function ii(i){return i<=.04045?i/12.92:((i+.055)/1.055)**2.4}p(ii,"srgbToLinear");function zh(i){return i<=.0031308?i*12.92:1.055*i**(1/2.4)-.055}p(zh,"linearToSrgb");function kh(i){let t=Math.min(1,Math.max(0,Number(i)||0));return Math.round(Math.min(1,Math.max(0,zh(t)))*255)}p(kh,"linearChannelToSrgbByte");function Jt(i){return!Array.isArray(i)||i.length<3?null:`#${i.slice(0,3).map(e=>kh(e).toString(16).padStart(2,"0")).join("")}`}p(Jt,"linearRgbToHex");var Ge=globalThis.Buffer,Vh=typeof TextEncoder<"u"?new TextEncoder:null;function Gh(i,t=0){let e=Number(i);return Number.isFinite(e)?e:t}p(Gh,"finiteNumber");function xn(i){return Math.min(Math.max(Gh(i),0),1)}p(xn,"clamp01");function si(i,t="utf-8"){if(Ge?.from)return Ge.from(String(i),t);if(t!=="utf-8"&&t!=="utf8"){let e=String(i),n=new Uint8Array(e.length);for(let s=0;s<e.length;s+=1)n[s]=e.charCodeAt(s)&255;return n}return Vh.encode(String(i))}p(si,"bytesFromString");function Kt(i,t=0){if(Ge?.alloc)return Ge.alloc(i,t);let e=new Uint8Array(i);return t&&e.fill(t),e}p(Kt,"allocBytes");function He(i,t=void 0){if(Ge?.concat)return Ge.concat(i,t);let e=t??i.reduce((r,o)=>r+o.length,0),n=new Uint8Array(e),s=0;for(let r of i)n.set(r,s),s+=r.length;return n}p(He,"concatBytes");function Lt(i){return new Uint8Array(i.buffer,i.byteOffset,i.byteLength)}p(Lt,"typedArrayBytes");function ds(i){return new DataView(i.buffer,i.byteOffset,i.byteLength)}p(ds,"viewFor");function nt(i,t,e){ds(i).setUint16(t,e,!0)}p(nt,"writeUInt16LE");function at(i,t,e){ds(i).setUint32(t,e,!0)}p(at,"writeUInt32LE");function ps(i,t,e){ds(i).setFloat32(t,e,!0)}p(ps,"writeFloatLE");function Vr(i,t,e,n){let s=String(e).slice(0,n);for(let r=0;r<s.length;r+=1)i[t+r]=s.charCodeAt(r)&127}p(Vr,"writeAscii");function kr(i,t=32){let e=(4-i.length%4)%4;return e?He([i,Kt(e,t)]):i}p(kr,"align4Buffer");function ye(i,t="model"){return String(i||t).trim().replace(/[\x00-\x1f<>:"/\\|?*]+/g,"-")||t}p(ye,"sanitizeName");function ms(i){let t=[1/0,1/0,1/0],e=[-1/0,-1/0,-1/0];for(let n=0;n<i.length;n+=3)t[0]=Math.min(t[0],i[n]),t[1]=Math.min(t[1],i[n+1]),t[2]=Math.min(t[2],i[n+2]),e[0]=Math.max(e[0],i[n]),e[1]=Math.max(e[1],i[n+1]),e[2]=Math.max(e[2],i[n+2]);return{min:t.map(n=>Number.isFinite(n)?n:0),max:e.map(n=>Number.isFinite(n)?n:0)}}p(ms,"boundsForPositions");function Gr(i,t="#d4d4d8"){let e=String(i||t).trim(),n=/^#(?:[0-9a-fA-F]{3}){1,2}$/.test(e)?e:t,s=n.length===4?`${n[1]}${n[1]}${n[2]}${n[2]}${n[3]}${n[3]}`:n.slice(1);return[parseInt(s.slice(0,2),16)/255,parseInt(s.slice(2,4),16)/255,parseInt(s.slice(4,6),16)/255]}p(Gr,"hexToRgb01");function Hr(i,t){let e=kr(He(t),0);i.buffers=[{byteLength:e.length}];let n=kr(si(JSON.stringify(i)),32),s=20+n.length+8+e.length,r=Kt(12);at(r,0,1179937895),at(r,4,2),at(r,8,s);let o=Kt(8);at(o,0,n.length),at(o,4,1313821514);let a=Kt(8);return at(a,0,e.length),at(a,4,5130562),He([r,o,n,a,e],s)}p(Hr,"buildGlb");function Hh(i,t){let e=i[t],n=i[t+1],s=i[t+2],r=i[t+3],o=i[t+4],a=i[t+5],c=i[t+6],l=i[t+7],h=i[t+8],u=r-e,f=o-n,d=a-s,m=c-e,g=l-n,_=h-s,x=f*_-d*g,M=d*m-u*_,y=u*g-f*m,v=Math.hypot(x,M,y);return v>1e-12?[x/v,M/v,y/v]:[0,0,1]}p(Hh,"triangleNormal");function Wr(i,{name:t="model"}={}){let e=i.positions||new Float32Array,n=Math.floor(e.length/9),s=Kt(84+n*50);Vr(s,0,`cad ${ye(t)}`,80),at(s,80,n);let r=84;for(let o=0;o<n;o+=1){let a=o*9,c=Hh(e,a);for(let l of c)ps(s,r,l),r+=4;for(let l=0;l<9;l+=1)ps(s,r,e[a+l]),r+=4;nt(s,r,0),r+=2}return s}p(Wr,"meshToBinaryStl");function xs(i){return String(i??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}p(xs,"xmlEscape");function gs(i){let t=gs.table;if(!t){t=new Uint32Array(256);for(let n=0;n<256;n+=1){let s=n;for(let r=0;r<8;r+=1)s=s&1?3988292384^s>>>1:s>>>1;t[n]=s>>>0}gs.table=t}let e=4294967295;for(let n of i)e=t[(e^n)&255]^e>>>8;return(e^4294967295)>>>0}p(gs,"crc32");function Xr(i){let t=[],e=[],n=0,s=0,r=33;for(let l of i){let h=si(l.name),u=l.body instanceof Uint8Array?l.body:si(String(l.body||"")),f=gs(u),d=Kt(30);at(d,0,67324752),nt(d,4,20),nt(d,6,0),nt(d,8,0),nt(d,10,s),nt(d,12,r),at(d,14,f),at(d,18,u.length),at(d,22,u.length),nt(d,26,h.length),nt(d,28,0),t.push(d,h,u);let m=Kt(46);at(m,0,33639248),nt(m,4,20),nt(m,6,20),nt(m,8,0),nt(m,10,0),nt(m,12,s),nt(m,14,r),at(m,16,f),at(m,20,u.length),at(m,24,u.length),nt(m,28,h.length),nt(m,30,0),nt(m,32,0),nt(m,34,0),nt(m,36,0),at(m,38,0),at(m,42,n),e.push(m,h),n+=d.length+h.length+u.length}let o=n,a=He(e),c=Kt(22);return at(c,0,101010256),nt(c,4,0),nt(c,6,0),nt(c,8,i.length),nt(c,10,i.length),at(c,12,a.length),at(c,16,o),nt(c,20,0),He([...t,a,c])}p(Xr,"zipStore");var ve=5126,Wh=5122,Xh=5120,qr=5123,qh=5125,ce=34962,$r=34963,$h=4,Yh=65535,Me=32767,_s=127;function ys(i){return i+3&-4}p(ys,"align4");function Zr(i,t){if(i.length>=t)return i;let e=new Uint8Array(t);return e.set(i,0),e}p(Zr,"padTo");function Yr(i,t,e,n){if(e===t)return Zr(i,ys(i.length));let s=new Uint8Array(n*e);for(let r=0;r<n;r+=1)s.set(i.subarray(r*t,(r+1)*t),r*e);return s}p(Yr,"strideElements");function Zh(i,t){let e=i[t],n=i[t+1],s=i[t+2],r=i[t+3],o=i[t+4],a=i[t+5],c=i[t+6],l=i[t+7],h=i[t+8],u=r-e,f=o-n,d=a-s,m=c-e,g=l-n,_=h-s,x=f*_-d*g,M=d*m-u*_,y=u*g-f*m,v=Math.hypot(x,M,y);return v>1e-12?[x/v,M/v,y/v]:[0,0,1]}p(Zh,"faceNormal");function Jh(i,t,{weldDecimals:e=5}={}){let n=Math.floor(i.length/3),s=10**e,r=p(u=>Math.round(u*s)/s,"q"),o=[],a=[],c=new Uint32Array(n),l=new Map,h=t&&t.length===i.length;for(let u=0;u*9<i.length;u+=1){let f=u*9,d=h?null:Zh(i,f);for(let m=0;m<3;m+=1){let g=f+m*3,_=i[g],x=i[g+1],M=i[g+2],y=h?t[g]:d[0],v=h?t[g+1]:d[1],b=h?t[g+2]:d[2],A=`${r(_)},${r(x)},${r(M)},${r(y)},${r(v)},${r(b)}`,w=l.get(A);w===void 0&&(w=o.length/3,l.set(A,w),o.push(_,x,M),a.push(y,v,b)),c[u*3+m]=w}}return{positions:new Float32Array(o),normals:new Float32Array(a),indices:c.subarray(0,Math.floor(i.length/3)*3)}}p(Jh,"weldMesh");function Kh(i,t){let e=i.length/3,n=new Int16Array(i.length),s=[Math.max(t.max[0]-t.min[0],1e-9),Math.max(t.max[1]-t.min[1],1e-9),Math.max(t.max[2]-t.min[2],1e-9)];for(let r=0;r<e;r+=1)for(let o=0;o<3;o+=1){let a=r*3+o,c=(i[a]-t.min[o])/s[o];n[a]=Math.max(-Me,Math.min(Me,Math.round(c*Me)))}return{array:n,scale:s.map(r=>r/Me),translation:[t.min[0],t.min[1],t.min[2]]}}p(Kh,"quantizePositions");function jh(i){let t=new Int8Array(i.length);for(let e=0;e<i.length;e+=1)t[e]=Math.max(-_s,Math.min(_s,Math.round(i[e]*_s)));return t}p(jh,"quantizeNormals");var Qh=.72,tu=.02;function _n(i,t){let e=Number(i?.[t]);return Number.isFinite(e)?xn(e):null}p(_n,"finishChannel");function eu(i,t,e=null,n=null){let s=Gr(i).map(xn).map(ii),r=_n(n,"opacity"),o=e==null?r===null?1:r:xn(e),a=_n(n,"roughness"),c=_n(n,"metalness"),l=_n(n,"clearcoat"),h=_n(n,"clearcoatRoughness"),u={name:ye(t||"material","material"),doubleSided:!0,extras:{cadSourceColor:!0},pbrMetallicRoughness:{baseColorFactor:[...s,o],roughnessFactor:a===null?Qh:a,metallicFactor:c===null?tu:c}};return o<1&&(u.alphaMode="BLEND"),l!==null&&l>0&&(u.extensions={KHR_materials_clearcoat:{clearcoatFactor:l,...h===null?{}:{clearcoatRoughnessFactor:h}}}),u}p(eu,"materialFor");var nu=[["translation",3,"VEC3"],["rotation",4,"VEC4"],["scale",3,"VEC3"]];function iu(i,{nodeIndexByKey:t,targetCountByKey:e,accessors:n,pushView:s}){let r=[];for(let o of Array.isArray(i)?i:[]){let a=[],c=[],l=new Map,h=p(u=>{let f=l.get(u);if(f!==void 0)return f;if(!u||!u.length)throw new Error("writeGlb: an animation channel needs a non-empty times array");return n.push({bufferView:s(Lt(u)),byteOffset:0,componentType:ve,count:u.length,type:"SCALAR",min:[u[0]],max:[u[u.length-1]]}),f=n.length-1,l.set(u,f),f},"timeAccessorFor");for(let u of o?.channels||[]){let f=t.get(String(u?.node));if(f===void 0)throw new Error(`writeGlb: animation channel targets node ${JSON.stringify(u?.node)}, which no primitive declared`);let d=h(u?.times||o?.times);if(u?.weights){let m=u?.times||o?.times,g=Number(u.targetCount),_=e.get(String(u.node))||0;if(!Number.isInteger(g)||g<1||g!==_)throw new Error(`writeGlb: weights channel on node ${JSON.stringify(u.node)} declares ${u.targetCount} morph targets, but its mesh has ${_}`);if(u.weights.length!==m.length*g)throw new Error(`writeGlb: weights channel on node ${JSON.stringify(u.node)} has ${u.weights.length} scalars for ${m.length} times x ${g} targets`);n.push({bufferView:s(Lt(u.weights)),byteOffset:0,componentType:ve,count:u.weights.length,type:"SCALAR"}),a.push({input:d,output:n.length-1,interpolation:"LINEAR"}),c.push({sampler:a.length-1,target:{node:f,path:"weights"}})}for(let[m,g,_]of nu){let x=u?.[m];x&&(n.push({bufferView:s(Lt(x)),byteOffset:0,componentType:ve,count:x.length/g,type:_}),a.push({input:d,output:n.length-1,interpolation:"LINEAR"}),c.push({sampler:a.length-1,target:{node:f,path:m}}))}}c.length&&r.push({name:ye(o?.name||"clip","clip"),samplers:a,channels:c})}return r}p(iu,"buildAnimations");function Jr(i,t={}){let{preset:e="export",name:n="model",units:s="mm",weldDecimals:r=5,encoder:o=null,occurrenceIdPrefix:a=null,upAxis:c="y",animations:l=null,nodeTransforms:h=null}=t,u=String(c).trim().toLowerCase();if(u!=="y"&&u!=="z")throw new Error(`writeGlb: upAxis must be "y" (glTF) or "z" (CAD), got ${JSON.stringify(c)}`);let f=String(a||t.sourceKind||ye(n,"model")),d=e==="render";if(d&&!o)throw new Error("writeGlb: preset 'render' requires meshoptimizer's MeshoptEncoder (await MeshoptEncoder.ready)");if(d&&(l||h))throw new Error("writeGlb: preset 'render' spends every node transform on dequantization, so it carries no animation or node TRS \u2014 use preset 'export' for an animated file");let m=Array.isArray(i?.primitives)&&i.primitives.length?i.primitives:[{positions:i?.positions,normals:i?.normals,color:t.color}],g=[],_=[],x=[],M=[],y=[],v=[],b=new Map,A=0,w=p(E=>{let F=ys(A);F>A&&(g.push(new Uint8Array(F-A)),A=F),g.push(E);let O=A;return A+=E.length,O},"appendBytes"),S=p((E,F)=>{let N={buffer:0,byteOffset:w(E),byteLength:E.length};return F&&(N.target=F),_.push(N),_.length-1},"pushView"),C=p((E,{count:F,stride:O,mode:N,target:U})=>{let z=w(E),B={byteLength:F*O,byteStride:O,extensions:{EXT_meshopt_compression:{buffer:0,byteOffset:z,byteLength:E.length,count:F,byteStride:O,mode:N}}};return U&&(B.target=U),_.push(B),_.length-1},"pushCompressedView");for(let E of m){let F=E?.positions instanceof Float32Array?E.positions:new Float32Array(E?.positions||[]);if(!F.length)continue;let O=Array.isArray(E?.targets)&&E.targets.length?E.targets:null;if(O){if(!E?.indices)throw new Error("writeGlb: morph targets need already-indexed input \u2014 a weld can merge two vertices a target moves apart, and the deltas would then be 1:1 with nothing");if(d)throw new Error("writeGlb: preset 'render' quantizes every attribute and carries no morph targets \u2014 use preset 'export' for a deforming file")}let N=E?.indices?{positions:F,normals:E.normals instanceof Float32Array&&E.normals.length===F.length?E.normals:new Float32Array(F.length),indices:E.indices}:Jh(F,E?.normals,{weldDecimals:r}),U=N.positions.length/3,z=ms(N.positions),B=null;if(typeof E?.colorAt=="function"){B=new Uint16Array(U*4);for(let _t=0;_t<U;_t+=1){let Ee=E.colorAt(N.positions[_t*3],N.positions[_t*3+1],N.positions[_t*3+2],N.normals[_t*3],N.normals[_t*3+1],N.normals[_t*3+2]);for(let Dt=0;Dt<3;Dt+=1)B[_t*4+Dt]=Math.round(ii(xn(Number(Ee?.[Dt])||0))*65535);B[_t*4+3]=65535}}let H,W,G=null,X,q,$=null,K=null;if(d){let _t=Kh(N.positions,z),Ee=Yr(Lt(_t.array),6,8,U),Dt=Yr(Lt(jh(N.normals)),3,4,U);H=C(o.encodeVertexBuffer(Ee,U,8),{count:U,stride:8,mode:"ATTRIBUTES",target:ce}),W=C(o.encodeVertexBuffer(Dt,U,4),{count:U,stride:4,mode:"ATTRIBUTES",target:ce}),B&&(G=C(o.encodeVertexBuffer(Lt(B),U,8),{count:U,stride:8,mode:"ATTRIBUTES",target:ce})),$=_t.scale,K=_t.translation,X={bufferView:H,byteOffset:0,componentType:Wh,count:U,type:"VEC3",min:[0,0,0],max:[Me,Me,Me]},q={bufferView:W,byteOffset:0,componentType:Xh,count:U,type:"VEC3",normalized:!0}}else H=S(Lt(N.positions),ce),W=S(Lt(N.normals),ce),B&&(G=S(Lt(B),ce)),X={bufferView:H,byteOffset:0,componentType:ve,count:U,type:"VEC3",min:z.min,max:z.max},q={bufferView:W,byteOffset:0,componentType:ve,count:U,type:"VEC3"};let Q=U<=Yh,j=Q?new Uint16Array(N.indices):new Uint32Array(N.indices),ct=Q?2:4,qt=d?C(o.encodeIndexBuffer(new Uint8Array(j.buffer,j.byteOffset,j.byteLength),j.length,ct),{count:j.length,stride:ct,mode:"TRIANGLES",target:$r}):S(Zr(Lt(j),ys(j.byteLength)),$r);x.push(X);let xt=x.length-1;x.push(q);let yt=x.length-1,Wt=null;B&&(x.push({bufferView:G,byteOffset:0,componentType:qr,count:U,type:"VEC4",normalized:!0}),Wt=x.length-1),x.push({bufferView:qt,byteOffset:0,componentType:Q?qr:qh,count:j.length,type:"SCALAR"});let he=x.length-1,At=O?.map((_t,Ee)=>{let Dt=_t?.positionDeltas;if(!(Dt instanceof Float32Array)||Dt.length!==N.positions.length)throw new Error(`writeGlb: morph target ${Ee} has ${Dt?.length??"no"} position deltas for ${N.positions.length/3} vertices`);let Bs=ms(Dt);x.push({bufferView:S(Lt(Dt),ce),byteOffset:0,componentType:ve,count:U,type:"VEC3",min:Bs.min,max:Bs.max});let zs={POSITION:x.length-1},je=_t?.normalDeltas;if(je){if(!(je instanceof Float32Array)||je.length!==N.positions.length)throw new Error(`writeGlb: morph target ${Ee} has ${je.length} normal deltas for ${N.positions.length/3} vertices`);x.push({bufferView:S(Lt(je),ce),byteOffset:0,componentType:ve,count:U,type:"VEC3"}),zs.NORMAL=x.length-1}return zs})||null;v.push(eu(B?"#ffffff":E?.color,E?.name,E?.opacity??null,E?.material??null));let ue={attributes:{POSITION:xt,NORMAL:yt,...Wt===null?{}:{COLOR_0:Wt}},indices:he,material:v.length-1,mode:$h,...At?{targets:At}:{}},kt=E?.node===void 0||E?.node===null?`\0primitive:${b.size}`:String(E.node),fe=b.get(kt);if(!fe)fe={key:kt,input:E,primitives:[],quantization:null,targetCount:At?At.length:0},b.set(kt,fe);else{if(fe.targetCount!==(At?At.length:0))throw new Error(`writeGlb: node ${JSON.stringify(kt)} mixes primitives with ${fe.targetCount} and ${At?At.length:0} morph targets, and glTF weights are per MESH`);if(d)throw new Error(`writeGlb: preset 'render' cannot put two primitives on node ${JSON.stringify(kt)}: each quantized primitive owns its node's transform`)}fe.primitives.push(ue),$&&(fe.quantization={scale:$,translation:K})}let T=new Map,D=new Map;for(let E of b.values()){D.set(E.key,E.targetCount),M.push({primitives:E.primitives,...E.targetCount?{weights:new Array(E.targetCount).fill(0)}:{}});let F={mesh:M.length-1,name:ye(E.input?.name||n,n),extras:{cadOccurrenceId:String(E.input?.occurrenceId||`${f}:${y.length}`),cadSourceKind:t.sourceKind||"mesh",cadUnits:s,cadUpAxis:u}};E.quantization&&(F.scale=E.quantization.scale,F.translation=E.quantization.translation);let O=h instanceof Map?h.get(E.key):null;O&&(O.translation&&(F.translation=[...O.translation]),O.rotation&&(F.rotation=[...O.rotation]),O.scale&&(F.scale=[...O.scale])),T.set(E.key,y.length),y.push(F)}let L=iu(l,{nodeIndexByKey:T,targetCountByKey:D,accessors:x,pushView:S}),P=d?["KHR_mesh_quantization","EXT_meshopt_compression"]:[],R=[...P];v.some(E=>E.extensions?.KHR_materials_clearcoat)&&R.push("KHR_materials_clearcoat");let I={asset:{version:"2.0",generator:"cadgen-js writeGlb"},scene:0,scenes:[{nodes:y.map((E,F)=>F)}],nodes:y,meshes:M,materials:v,bufferViews:_,accessors:x,...L.length?{animations:L}:{}};return R.length&&(I.extensionsUsed=R),P.length&&(I.extensionsRequired=P),Hr(I,g)}p(Jr,"writeGlb");var vs=["stl","glb","3mf"],su=4194304,jr="#d4d4d8",Qr=["roughness","metalness","clearcoat","clearcoatRoughness","opacity"];function Ms(i){if(!i||typeof i!="object"||Array.isArray(i))return null;let t={};for(let e of Qr){let n=Number(i[e]);Number.isFinite(n)&&(t[e]=Math.min(1,Math.max(0,n)))}return Object.keys(t).length?t:null}p(Ms,"occurrenceMaterial");function Kr(i){return i?`|${Qr.map(t=>t in i?i[t]:"").join(",")}`:""}p(Kr,"materialKey");function to(i,t,e,n=jr){let s=String(t?.component||""),r=Jt(t?.color),o=Jt(i?.components?.[s]?.color)||null,a=Jt(e?.partColor)||null,c=r||o||a||n;return(e?.faceRanges||[]).map(l=>Jt(l.color)||c)}p(to,"occurrenceFaceRangeColors");function Ss(i,t,e,n,s,r){s[r]=i[0]*t+i[1]*e+i[2]*n+i[3],s[r+1]=i[4]*t+i[5]*e+i[6]*n+i[7],s[r+2]=i[8]*t+i[9]*e+i[10]*n+i[11]}p(Ss,"transformPoint");function bs(i){return i[0]*(i[5]*i[10]-i[6]*i[9])-i[1]*(i[4]*i[10]-i[6]*i[8])+i[2]*(i[4]*i[9]-i[5]*i[8])}p(bs,"determinant3");function As(i){let t=i[0],e=i[1],n=i[2],s=i[4],r=i[5],o=i[6],a=i[8],c=i[9],l=i[10],h=r*l-o*c,u=o*a-s*l,f=s*c-r*a,d=t*h+e*u+n*f;if(!Number.isFinite(d)||Math.abs(d)<1e-30)return null;let m=1/d;return[h*m,u*m,f*m,(n*c-e*l)*m,(t*l-n*a)*m,(e*a-t*c)*m,(e*o-n*r)*m,(n*s-t*o)*m,(t*r-e*s)*m]}p(As,"normalMatrix3");function ws(i){return!Array.isArray(i)||i.length<12?!0:[1,0,0,0,0,1,0,0,0,0,1,0].every((e,n)=>i[n]===e)}p(ws,"identityTransform");function Ts(i,t,e={}){let n=e.defaultColor||jr,s=new Map(Object.entries(i.components||{}).map(([g,_])=>[g,Jt(_?.color)])),r=Math.max(1,Math.floor(Number(e.maxPrimitiveTriangles)||su)),o=e.perOccurrence===!0,a=e.hiddenOccurrenceIds instanceof Set?e.hiddenOccurrenceIds:null,c=e.occurrenceOpacity instanceof Map?e.occurrenceOpacity:null,l=e.occurrenceOverrides instanceof Map?e.occurrenceOverrides:null;if(l&&!o)throw new Error("buildPackageMeshPrimitives: occurrenceOverrides needs perOccurrence \u2014 an override is keyed by occurrence, and the flat soup has no occurrence to key it to");let h=[],u=new Map,f=-1;for(let g of i.occurrences||[]){f+=1;let _=String(g.component||""),x=t.get(_);if(!x)continue;let M=String(g.id||_);if(a?.has(M))continue;let y=Jt(g.color),v=s.get(_)||null,b=Jt(x.partColor)||null,A=y||v||b||n,w=c?.has(M)?c.get(M):null,S=Ms(g.material),C=Kr(S),T=l?.get(M);if(T){T.forEach((I,E)=>{let F=`${String(f).padStart(8,"0")}|${I.color}${Kr(I.material||null)}|${String(E).padStart(4,"0")}`;u.set(F,{override:{...I,node:M,name:String(g.name||M),occurrenceId:M,...w==null?{}:{opacity:w}}})});continue}let D=Array.isArray(g.transform)?g.transform:null,L=D===null||ws(D),P=!L&&bs(D)<0,R=L?null:As(D);for(let I of x.faceRanges||[]){let E=Number(I.indexCount)||0,F=Math.max(0,Math.ceil(E/3));if(!F)continue;let O=Jt(I.color)||A,N=(o?`${String(f).padStart(8,"0")}|${O}`:O)+C,U=u.get(N);U||u.set(N,U={color:O,material:S,chunks:[],node:o?M:null,name:o?String(g.name||M):null,occurrenceId:o?M:null,opacity:w});let z=U.chunks[U.chunks.length-1];(!z||z.triangles+F>r)&&(z={triangles:0,floatCount:0,positions:null,normals:null,offset:0},U.chunks.push(z)),z.triangles+=F,z.floatCount+=F*9,h.push({tessellation:x,range:I,color:O,chunk:z,transform:L?null:D,mirrored:P,nm:R})}}for(let g of u.values())for(let _ of g.chunks||[])_.positions=new Float32Array(_.floatCount),_.normals=new Float32Array(_.floatCount);for(let g of h){let{positions:_,normals:x,indices:M}=g.tessellation,{range:y,transform:v,mirrored:b,nm:A}=g,w=g.chunk,S=w.positions,C=w.normals,T=w.offset,D=b?[0,2,1]:[0,1,2];for(let L=y.indexStart;L<y.indexStart+y.indexCount;L+=3)for(let P of D){let R=M[L+P],I=_[R*3],E=_[R*3+1],F=_[R*3+2];v===null?(S[T]=I,S[T+1]=E,S[T+2]=F):Ss(v,I,E,F,S,T);let O=x[R*3],N=x[R*3+1],U=x[R*3+2],z=O,B=N,H=U;A&&(z=A[0]*O+A[1]*N+A[2]*U,B=A[3]*O+A[4]*N+A[5]*U,H=A[6]*O+A[7]*N+A[8]*U);let W=Math.hypot(z,B,H)||1;C[T]=z/W,C[T+1]=B/W,C[T+2]=H/W,T+=3}w.offset=T}let d=[...u.entries()].sort(([g],[_])=>g<_?-1:1).flatMap(([,g])=>g.override?[g.override]:g.chunks.map(_=>({color:g.color,positions:_.positions,normals:_.normals,...g.node===null?{}:{node:g.node,name:g.name,occurrenceId:g.occurrenceId},...g.opacity===null||g.opacity===void 0?{}:{opacity:g.opacity},...g.material===null?{}:{material:g.material}}))).filter(g=>g.indices?g.indices.length>=3:g.positions.length>=9),m=d.reduce((g,_)=>g+(_.indices?_.indices.length/3:_.positions.length/9),0);return{primitives:d,triangleCount:m}}p(Ts,"buildPackageMeshPrimitives");function ru({primitives:i},{name:t="model"}={}){let e=0;for(let r of i)e+=r.positions.length;let n=new Float32Array(e),s=0;for(let r of i)n.set(r.positions,s),s+=r.positions.length;return Wr({positions:n},{name:t})}p(ru,"packageMeshToStl");var yn=.001;function ri(i,t){let e=new Float32Array(i.length);for(let n=0;n<i.length;n+=3)e[n]=i[n]*t,e[n+1]=i[n+2]*t,e[n+2]=-i[n+1]*t;return e}p(ri,"rotateToYUp");function ou(i){return i.map(t=>({positionDeltas:ri(t.positionDeltas,yn),...t.normalDeltas?{normalDeltas:ri(t.normalDeltas,1)}:{}}))}p(ou,"yUpTargets");function au(i){let t=i.verify;if(!t)return;let{vertexIds:e,posed:n}=t;for(let s=0;s<n.length;s+=1){let r=i.targets[s].positionDeltas;for(let o=0;o<e.length;o+=1){let a=e[o]*3,c=[n[s][o*3]*yn,n[s][o*3+2]*yn,-n[s][o*3+1]*yn];for(let l=0;l<3;l+=1){let h=i.positions[a+l]+r[a+l];if(Math.abs(h-c[l])>cu)throw new Error(`packageMeshExport: morph target ${s} of ${i.occurrenceId||i.node} rebuilds vertex ${e[o]} as ${h} where the posed tube is ${c[l]} (axis ${l}) \u2014 base and deltas are not in the same space`)}}}}p(au,"verifyMorphReconstruction");var cu=1e-6;function lu(i){return i.map(t=>{let e={...t,positions:ri(t.positions,yn),normals:ri(t.normals,1),...t.targets?{targets:ou(t.targets)}:{}};return e.targets&&(au(e),delete e.verify),e})}p(lu,"yUpPrimitives");function hu({primitives:i},{name:t="model",animation:e=null}={}){return Jr({primitives:lu(i)},{preset:"export",name:t,sourceKind:"step",units:"m",upAxis:"y",...e?{animations:[e],nodeTransforms:e.rest||null}:{}})}p(hu,"packageMeshToGlb");function uu({primitives:i},{name:t="model"}={}){let e=i.map((c,l)=>`      <base name="material-${l}" displaycolor="${xs(c.color.toUpperCase())}FF"/>`).join(`
`),n=[],s=[];i.forEach((c,l)=>{let h=[],u=[],f=new Map,d=c.positions,m=p((_,x,M)=>{let y=`${_}:${x}:${M}`,v=f.get(y);return v===void 0&&(v=f.size,f.set(y,v),h.push(`        <vertex x="${_}" y="${x}" z="${M}"/>`)),v},"vertexId");for(let _=0;_<d.length;_+=9){let x=m(d[_],d[_+1],d[_+2]),M=m(d[_+3],d[_+4],d[_+5]),y=m(d[_+6],d[_+7],d[_+8]);x!==M&&M!==y&&y!==x&&u.push(`        <triangle v1="${x}" v2="${M}" v3="${y}"/>`)}let g=l+2;n.push(`    <object id="${g}" type="model" pid="1" pindex="${l}">
      <mesh>
        <vertices>
${h.join(`
`)}
        </vertices>
        <triangles>
${u.join(`
`)}
        </triangles>
      </mesh>
    </object>`),s.push(`    <item objectid="${g}"/>`)});let r=`<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">
  <metadata name="Title">${xs(t)}</metadata>
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
`;return Xr([{name:"[Content_Types].xml",body:`<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
`},{name:"_rels/.rels",body:`<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
`},{name:"3D/3dmodel.model",body:r}])}p(uu,"packageMeshTo3mf");function eo(i,t,e={}){let n=String(t||"").toLowerCase();if(e.animation&&n!=="glb")throw new Error(`${n||"(no format)"} carries no animation: only glb does \u2014 export the clip as .glb, or drop the animation for a static mesh`);if(n==="stl")return{body:ru(i,e),contentType:"model/stl",extension:".stl"};if(n==="glb")return{body:hu(i,e),contentType:"model/gltf-binary",extension:".glb"};if(n==="3mf")return{body:uu(i,e),contentType:"model/3mf",extension:".3mf"};throw new Error(`Unsupported package mesh export format: ${t}`)}p(eo,"packageMeshToFormat");var Se=1e-7,Es=.05,Cs={vertices:0,worstReach:0};var no=7e5,fu=128,$e=p((i,t)=>i.map((e,n)=>e+t[n]),"add"),Nt=p((i,t)=>i.map((e,n)=>e-t[n]),"sub"),bt=p((i,t)=>i.map(e=>e*t),"mul"),ut=p((i,t)=>i.reduce((e,n,s)=>e+n*t[s],0),"dot"),le=p((i,t)=>[i[1]*t[2]-i[2]*t[1],i[2]*t[0]-i[0]*t[2],i[0]*t[1]-i[1]*t[0]],"cross"),zt=p(i=>Math.hypot(...i),"length"),io=p((i,t)=>(i[0]-t[0])**2+(i[1]-t[1])**2+(i[2]-t[2])**2,"distanceSq");function du(i,t){let e=0;for(let n=0;n<3;n++)e+=Math.max(i.min[n]-t[n],0,t[n]-i.max[n])**2;return e}p(du,"boundsDistanceSq");function it(i){throw new Error(`animation deformTube: ${i}`)}p(it,"fail");function Tt(i,t){return(!Array.isArray(i)||i.length!==3||!i.every(Number.isFinite))&&it(`${t} must be a finite vec3`),i.slice()}p(Tt,"vector");function Xe(i,t){let e=zt(i);return e<Se&&it(`${t} must be nonzero`),bt(i,1/e)}p(Xe,"unit");function Ye(i,t,e){(!i||typeof i!="object"||Array.isArray(i))&&it(`${e} must be an object`);for(let n of Object.keys(i))t.includes(n)||it(`unknown ${e} key ${JSON.stringify(n)}; expected ${t.join(", ")}`)}p(Ye,"keys");function oi(i,t,e){let n=Math.cos(e),s=Math.sin(e);return $e($e(bt(i,n),bt(le(t,i),s)),bt(t,ut(t,i)*(1-n)))}p(oi,"rotate");function Mn(i,t){let e=1-t;return[0,1,2].map(n=>e*e*e*i[0][n]+3*e*e*t*i[1][n]+3*e*t*t*i[2][n]+t*t*t*i[3][n])}p(Mn,"bezierAt");function Ze(i,t){let e=1-t;return[0,1,2].map(n=>3*e*e*(i[1][n]-i[0][n])+6*e*t*(i[2][n]-i[1][n])+3*t*t*(i[3][n]-i[2][n]))}p(Ze,"bezierDerivative");function co(i,t){return[0,1,2].map(e=>6*(1-t)*(i[2][e]-2*i[1][e]+i[0][e])+6*t*(i[3][e]-2*i[2][e]+i[1][e]))}p(co,"bezierSecond");var pu=[0,.5384693101056831,-.5384693101056831,.906179845938664,-.906179845938664],mu=[.5688888888888889,.4786286704993665,.4786286704993665,.2369268850561891,.2369268850561891];function vn(i,t,e){let n=(t+e)/2,s=(e-t)/2,r=0;for(let o=0;o<5;o++){let a=n+s*pu[o],c=1-a,l=3*c*c,h=6*c*a,u=3*a*a,f=l*(i[1][0]-i[0][0])+h*(i[2][0]-i[1][0])+u*(i[3][0]-i[2][0]),d=l*(i[1][1]-i[0][1])+h*(i[2][1]-i[1][1])+u*(i[3][1]-i[2][1]),m=l*(i[1][2]-i[0][2])+h*(i[2][2]-i[1][2])+u*(i[3][2]-i[2][2]);r+=mu[o]*Math.hypot(f,d,m)}return s*r}p(vn,"bezierLength");function lo(i,t,e){let n=le(t,e),s=zt(n),r=ut(t,e);return s<Se?(r<0&&it("path tangent reverses"),i.slice()):oi(i,bt(n,1/s),Math.atan2(s,r))}p(lo,"transport");function gu(i){let t=[{t:0,s:0,tangent:i.tangent,normal:i.normal}],e=p((n,s,r=0)=>{let o=(n+s)/2,a=vn(i.points,n,s),c=vn(i.points,n,o),l=vn(i.points,o,s),h=Xe(Ze(i.points,n),"Bezier tangent"),u=Xe(Ze(i.points,s),"Bezier tangent");if(r<20&&(s-n>1/128||Math.abs(a-c-l)>1e-9||ut(h,u)<.9999)){e(n,o,r+1),e(o,s,r+1);return}ut(h,u)<.99&&it("Bezier has a cusp or unresolved tangent");let f=t.at(-1);t.push({t:s,s:f.s+c+l,tangent:u,normal:lo(f.normal,f.tangent,u)})},"append");e(0,1),i.table=t,i.length=t.at(-1).s}p(gu,"buildBezierTable");function ho(i,t){let e=i.table,n=0,s=e.length-1;for(;s-n>1;){let c=n+s>>1;e[c].s<t?n=c:s=c}let r=e[n],o=e[s],a=r.t+(o.t-r.t)*(t-r.s)/(o.s-r.s);for(let c=0;c<3;c++){let l=r.s+vn(i.points,r.t,a)-t;if(Math.abs(l)<1e-11)break;a=Math.max(r.t,Math.min(o.t,a-l/zt(Ze(i.points,a))))}return{t:a,lower:r}}p(ho,"bezierParameter");function uo(i,t){return i.kind==="line"?$e(i.start,bt(i.tangent,t)):i.kind==="bezier"?Mn(i.points,ho(i,t).t):$e(i.center,oi(i.radial,i.axis,t/i.radius*i.sign))}p(uo,"segmentPoint");function Rs(i,t){if(i.kind==="bezier"){let{t:a,lower:c}=ho(i,t),l=Ze(i.points,a),h=zt(l),u=bt(l,1/h),f=lo(c.normal,c.tangent,u),d=co(i.points,a),m=bt(Nt(d,bt(u,ut(d,u))),1/(h*h));return{point:Mn(i.points,a),tangent:u,normal:f,binormal:le(u,f),curvature:m}}let e=i.kind==="arc"?t/i.radius*i.sign:0,n=e?oi(i.tangent,i.axis,e):i.tangent,s=e?oi(i.normal,i.axis,e):i.normal,r=uo(i,t),o=i.kind==="arc"?bt(Nt(i.center,r),1/(i.radius*i.radius)):[0,0,0];return{point:r,tangent:n,normal:s,binormal:le(n,s),curvature:o}}p(Rs,"segmentFrame");var ai={line:["kind","start","end"],arc:["kind","center","axis","start","sweepDeg"],bezier:["kind","points"]};function xu(i,t){if(Ye(i,ai[i.kind]||ai.arc,`segment ${t}`),i.kind==="line"){let e=Tt(i.start,"start"),n=Tt(i.end,"end"),s=Nt(n,e);return{kind:"line",start:e,end:n,tangent:Xe(s,"line"),length:zt(s),radius:1/0}}if(i.kind==="arc"){let e=Tt(i.center,"center"),n=Tt(i.start,"start"),s=Xe(Tt(i.axis,"axis"),"axis"),r=Nt(n,e),o=zt(r),a=i.sweepDeg*Math.PI/180;(!Number.isFinite(a)||Math.abs(a)<Se||Math.abs(a)>2*Math.PI+Se)&&it("arc sweepDeg must be nonzero and at most 360 degrees"),(o<Se||Math.abs(ut(r,s))>Se*Math.max(1,o))&&it("arc start must be in its normal plane with nonzero radius");let c=Math.sign(a),l=bt(le(s,r),c/o),h={kind:"arc",center:e,start:n,axis:s,radial:r,radius:o,sign:c,tangent:l,length:o*Math.abs(a)};return h.end=uo(h,h.length),h}if(i.kind==="bezier"){(!Array.isArray(i.points)||i.points.length!==4)&&it("Bezier points must contain four vec3 control points");let e=i.points.map(n=>Tt(n,"Bezier point"));return{kind:"bezier",points:e,start:e[0],end:e[3],tangent:Xe(Ze(e,0),"Bezier tangent"),radius:1/0}}return it(`unknown segment kind ${JSON.stringify(i.kind)}; expected line, arc, bezier`)}p(xu,"compileSegment");function _u(i){return Math.min(...i.table.map(t=>{let e=Ze(i.points,t.t),n=co(i.points,t.t),s=zt(e);return Math.pow(s,3)/zt(le(e,n))}))}p(_u,"sampledBezierRadius");function yu(i){if(i.kind==="arc")return{min:i.center.map(e=>e-i.radius),max:i.center.map(e=>e+i.radius)};let t=i.kind==="bezier"?i.points:[i.start,i.end];return{min:[0,1,2].map(e=>Math.min(...t.map(n=>n[e]))),max:[0,1,2].map(e=>Math.max(...t.map(n=>n[e])))}}p(yu,"segmentBounds");function vu(i){Ye(i,["segments","normal"],"path"),(!Array.isArray(i.segments)||!i.segments.length)&&it("path needs at least one segment"),i.normal===void 0&&it("path normal is required: give both the rest and the posed path an explicit transverse normal seed");let t=Tt(i.normal,"normal"),e=0,n=null,s=i.segments.map((o,a)=>{let c=xu(o,a);if(n){zt(Nt(n.end,c.start))>1e-5&&it(`path discontinuity before segment ${a}`);let l=Rs(n,n.length);ut(l.tangent,c.tangent)<1-1e-7&&it(`path is not tangent-continuous before segment ${a}`),c.normal=l.normal}else c.normal=Xe(Nt(t,bt(c.tangent,ut(t,c.tangent))),"path normal transverse to first tangent");return c.kind==="bezier"&&gu(c),c.offset=e,c.bounds=yu(c),e+=c.length,n=c,c}),r={segments:s,length:e};return Object.defineProperty(r,"minRadius",{get(){for(let o of s)o.kind==="bezier"&&o.radius===1/0&&(o.radius=_u(o));return Math.min(...s.map(o=>o.radius))}}),r}p(vu,"compileTubePath");function ci(i,t){Number.isFinite(t)||it("path distance must be finite");let e=t<=0?i.segments[0]:i.segments.find(o=>t<=o.offset+o.length)||i.segments.at(-1),n=t-e.offset,s=Math.max(0,Math.min(e.length,n)),r=Rs(e,s);return n!==s&&(r.point=$e(r.point,bt(r.tangent,n-s))),r}p(ci,"sampleTubePath");function Mu(i){if(!i.tablePoints){let t=new Float64Array(i.table.length*3);i.table.forEach((e,n)=>{let s=Mn(i.points,e.t);t[n*3]=s[0],t[n*3+1]=s[1],t[n*3+2]=s[2]}),i.tablePoints=t}return i.tablePoints}p(Mu,"tablePoints");function Su(i,t){let e=Mu(i),n=0,s=1/0;for(let l=0;l<i.table.length;l++){let h=(t[0]-e[l*3])**2+(t[1]-e[l*3+1])**2+(t[2]-e[l*3+2])**2;h<s&&(s=h,n=l)}let r=i.table[Math.max(0,n-1)].t,o=i.table[Math.min(i.table.length-1,n+1)].t;for(let l=0;l<35;l++){let h=r+(o-r)/3,u=o-(o-r)/3;io(t,Mn(i.points,h))<io(t,Mn(i.points,u))?o=u:r=h}let a=(r+o)/2,c=i.table.findLast(l=>l.t<=a)||i.table[0];return c.s+vn(i.points,c.t,a)}p(Su,"closestBezierDistance");function bu(i,t){let e=Nt(t,i.center),n=Math.atan2(ut(le(i.radial,e),i.axis),ut(i.radial,e))*i.sign;n<0&&(n+=2*Math.PI);let s=n*i.radius;return s>i.length?zt(Nt(t,i.start))<zt(Nt(t,i.end))?0:i.length:s}p(bu,"closestArcDistance");function fo(i,t){let e=null,n=i.segments.map(s=>({segment:s,bound:du(s.bounds,t)})).sort((s,r)=>s.bound-r.bound);for(let{segment:s,bound:r}of n){if(e&&r>e.distanceSq+1e-12)break;let o;s.kind==="line"?o=ut(Nt(t,s.start),s.tangent):s.kind==="bezier"?o=Su(s,t):o=bu(s,t),o=Math.max(0,Math.min(s.length,o));let a=Rs(s,o),c=Nt(t,a.point),l=ut(c,c);(!e||l<e.distanceSq)&&(e={distance:s.offset+o,distanceSq:l,transverse:[ut(c,a.normal),ut(c,a.binormal)],axial:ut(c,a.tangent)})}return e}p(fo,"projectTubePath");var We=new Map;function so(i){let t=JSON.stringify(i),e=We.get(t);return e?We.delete(t):e=vu(i),We.set(t,e),We.size>fu&&We.delete(We.keys().next().value),e}p(so,"cachedCompile");function ro(i){Ye(i,["segments","normal"],"path"),(!Array.isArray(i.segments)||!i.segments.length)&&it("path needs at least one segment"),i.normal===void 0&&it("path normal is required: give both the rest and the posed path an explicit transverse normal seed");let t=Tt(i.normal,"normal"),e=i.segments.map((n,s)=>(Ye(n,ai[n.kind]||ai.arc,`segment ${s}`),n.kind==="line"?{kind:"line",start:Tt(n.start,"start"),end:Tt(n.end,"end")}:n.kind==="arc"?{kind:"arc",center:Tt(n.center,"center"),axis:Tt(n.axis,"axis"),start:Tt(n.start,"start"),sweepDeg:n.sweepDeg}:n.kind==="bezier"?((!Array.isArray(n.points)||n.points.length!==4)&&it("Bezier points must contain four vec3 control points"),{kind:"bezier",points:n.points.map(r=>Tt(r,"Bezier point"))}):it(`unknown segment kind ${JSON.stringify(n.kind)}; expected line, arc, bezier`)));return{normal:t,segments:e}}p(ro,"canonicalPathSpec");function qe(i,t){if(i===t)return!0;if(Array.isArray(i))return!Array.isArray(t)||i.length!==t.length?!1:i.every((e,n)=>qe(e,t[n]));if(i&&typeof i=="object"){if(!t||typeof t!="object"||Array.isArray(t))return!1;let e=Object.keys(i);return e.length===Object.keys(t).length&&e.every(n=>qe(i[n],t[n]))}return!1}p(qe,"sameNumbers");function li(i,t){return i===t?!0:!i||!t?!1:i.twistDeg===t.twistDeg&&i.maxSegmentLength===t.maxSegmentLength&&qe(i.braid,t.braid)&&qe(i.restSpec,t.restSpec)&&qe(i.pathSpec,t.pathSpec)}p(li,"sameTubeDeformation");function po(i,t){return i.maxSegmentLength===t.maxSegmentLength&&qe(i.restSpec,t.restSpec)}p(po,"sameTubeRestShape");function be(i){return{...i,rest:so(i.restSpec),path:so(i.pathSpec)}}p(be,"compileDeformation");function mo(i){Ye(i,["rest","path","twistDeg","maxSegmentLength","braid"],"deformation");let t=i.twistDeg??0;Number.isFinite(t)||it("twistDeg must be finite");let e=i.maxSegmentLength??1;(!Number.isFinite(e)||e<.05)&&it("maxSegmentLength must be at least 0.05 mm");let n=null;if(i.braid){Ye(i.braid,["pitch","depth","strands"],"braid");let{pitch:s,depth:r,strands:o}=i.braid;Number.isFinite(s)&&s>0&&Number.isFinite(r)&&r>=0&&Number.isInteger(o)&&o>=2&&o<=64&&o%2===0||it("braid needs positive pitch, nonnegative depth, and an even strand count from 2 to 64"),n={pitch:s,depth:r,strands:o}}return{restSpec:ro(i.rest),pathSpec:ro(i.path),twistDeg:t,maxSegmentLength:e,braid:n}}p(mo,"normalizeTubeDeformation");var Au=p(i=>JSON.stringify([i.restSpec,i.maxSegmentLength]),"restMappingKey");function oo(i,t,e){let n=[];for(let s=0;s<i.length;s++){let r=i[s],o=i[(s+1)%i.length],a=e?r[0]>=t:r[0]<=t,c=e?o[0]>=t:o[0]<=t;if(a&&n.push(r),a!==c){let l=(t-r[0])/(o[0]-r[0]);n.push(r.map((h,u)=>h+l*(o[u]-h)))}}return n.filter((s,r)=>!r||Math.abs(s[1]-n[r-1][1])+Math.abs(s[2]-n[r-1][2])+Math.abs(s[3]-n[r-1][3])>1e-10)}p(oo,"clipPolygon");function wu(i,t,e,n,s){if(s>=e.length)return{geometry:t,sourceTriangles:null};let r=t.attributes.position,o=new i.Vector3,a=new Float64Array(r.count),c=new Map;for(let x=0;x<r.count;x++){let M=[r.getX(x),r.getY(x),r.getZ(x)].join(","),y=c.get(M);y===void 0&&(o.fromBufferAttribute(r,x).applyMatrix4(n),y=fo(e,o.toArray()).distance,c.set(M,y)),a[x]=y}c.clear();let l=t.index?.count??r.count;if(l%3)return{geometry:t.clone(),sourceTriangles:null};let h=Object.entries(t.attributes),u=Object.fromEntries(h.map(([x])=>[x,[]])),f=[],d=[],m=new Map,g=p(x=>t.index?t.index.getX(x):x,"index");for(let x=0;x<l;x+=3){let M=[g(x),g(x+1),g(x+2)],y=M.map(w=>a[w]),v=y.map((w,S)=>[w,...[0,1,2].map(C=>S===C?1:0)]),b=Math.floor(Math.min(...y)/s),A=Math.floor(Math.max(...y)/s);for(let w=b;w<=A;w++){let S=oo(oo(v,w*s,!0),(w+1)*s,!1);for(let C=1;C<S.length-1;C++){let T=[S[0],S[C],S[C+1]],D=Nt(T[1].slice(1),T[0].slice(1)),L=Nt(T[2].slice(1),T[0].slice(1));if(!(zt(le(D,L))<1e-12)){f.push(x/3),f.length>no&&it(`refined tube exceeds ${no} triangles; increase maxSegmentLength`);for(let P of T){let R=M.map((E,F)=>[E,Math.round(P[F+1]*1e10)]).filter(([,E])=>E).sort((E,F)=>E[0]-F[0]).map(E=>E.join(":")).join(","),I=m.get(R);if(I===void 0){I=m.size,m.set(R,I);for(let[E,F]of h)for(let O=0;O<F.itemSize;O++)u[E].push(M.reduce((N,U,z)=>N+P[z+1]*F.getComponent(U,O),0))}d.push(I)}}}}}let _=t.clone();for(let[x,M]of h)_.setAttribute(x,new i.Float32BufferAttribute(u[x],M.itemSize));return _.setIndex(d),_.clearGroups(),{geometry:_,sourceTriangles:new Uint32Array(f)}}p(wu,"refineRestMesh");function Tu(i,t,e,n,s,r=!1){let o=[],a=r?new Float32Array(t.count):new Uint32Array(t.count),c=new Map,l=new i.Vector3,h=new i.Matrix3().getNormalMatrix(s),u=new i.Vector3;for(let d=0;d<t.count;d++){let m=[t.getX(d),t.getY(d),t.getZ(d),...e?[e.getX(d),e.getY(d),e.getZ(d)]:[]].join(","),g=c.get(m);if(g!==void 0){a[d]=g;continue}let _=o.length/8;c.set(m,_),a[d]=_,l.fromBufferAttribute(t,d).applyMatrix4(s);let x=fo(n,[l.x,l.y,l.z]),M=ci(n,x.distance),y=$e(bt(M.normal,x.transverse[0]),bt(M.binormal,x.transverse[1])),v=1-ut(M.curvature,y);v<=Se&&it("rest mesh crosses the centerline curvature radius");let b=[0,0,0];if(e){u.fromBufferAttribute(e,d).applyNormalMatrix(h);let A=[u.x,u.y,u.z];b=[ut(A,M.normal),ut(A,M.binormal),ut(A,M.tangent)]}o.push(x.distance/n.length,...x.transverse,x.axial,...b,v)}let f=r?new Float32Array(Math.ceil(o.length/4096)*4096):new Float64Array(o.length);return f.set(o),{values:f,indices:a,gpu:r}}p(Tu,"mappingFor");function Eu(i,t,e,n,s,r){let{path:o,rest:a}=s,c=new i.Vector3,l=new i.Vector3,h=new i.Matrix3().getNormalMatrix(r),u=s.twistDeg*Math.PI/180,f=Math.cos(u),d=Math.sin(u),m=o.length/a.length,g=new Map,_=n.values,x=new Map;for(let M=0;M<t.count;M++){let y=n.indices[M],v=x.get(y);if(v!==void 0){t.setXYZ(M,t.getX(v),t.getY(v),t.getZ(v)),e&&e.setXYZ(M,e.getX(v),e.getY(v),e.getZ(v));continue}x.set(y,M);let b=y*8,A=_[b],w=g.get(A);w||(w=ci(o,A*o.length),g.set(A,w));let S=f*_[b+1]-d*_[b+2],C=d*_[b+1]+f*_[b+2],T=w.normal[0]*S+w.binormal[0]*C,D=w.normal[1]*S+w.binormal[1]*C,L=w.normal[2]*S+w.binormal[2]*C,P=w.curvature[0]*T+w.curvature[1]*D+w.curvature[2]*L;if(1-P<=Es){let I=(1-Es)/P;T*=I,D*=I,L*=I,Cs.vertices+=1,Cs.worstReach=Math.max(Cs.worstReach,P),P=1-Es}let R=1-P;if(c.set(w.point[0]+T+_[b+3]*w.tangent[0],w.point[1]+D+_[b+3]*w.tangent[1],w.point[2]+L+_[b+3]*w.tangent[2]).applyMatrix4(r),t.setXYZ(M,c.x,c.y,c.z),e){let I=f*_[b+4]-d*_[b+5],E=d*_[b+4]+f*_[b+5],F=_[b+6]*_[b+7]/(R*m);l.set(I*w.normal[0]+E*w.binormal[0]+F*w.tangent[0],I*w.normal[1]+E*w.binormal[1]+F*w.tangent[1],I*w.normal[2]+E*w.binormal[2]+F*w.tangent[2]).applyNormalMatrix(h),e.setXYZ(M,l.x,l.y,l.z)}}t.needsUpdate=!0,e&&(e.needsUpdate=!0)}p(Eu,"updateAttribute");var ao=new WeakMap;function Cu(i,t){return`${Au(i)}|${t.elements.map(e=>Number(e).toPrecision(9)).join(",")}`}p(Cu,"restPreparationKey");function Ru(i,t,e,n){let s=ao.get(t);s||(s=new Map,ao.set(t,s));let r=Cu(e,n),o=s.get(r);if(!o){let a=wu(i,t,e.rest,n,e.maxSegmentLength);o={restSource:a.geometry,sourceTriangles:a.sourceTriangles,mappings:new Map},s.set(r,o)}return o}p(Ru,"prepareRestSurface");function Iu(i,t,e,n,s){let r=s?"gpu":"exact",o=t.mappings.get(r);return o||(o=Tu(i,t.restSource.attributes.position,t.restSource.attributes.normal,e.rest,n,s),t.mappings.set(r,o)),o}p(Iu,"preparedMapping");function go(i,t,e,n){let s=Ru(i,t,e,n);return{geometry:s.restSource,sourceTriangles:s.sourceTriangles,mapping:Iu(i,s,e,n,!1),vertexCount:s.restSource.attributes.position.count}}p(go,"prepareTubeBake");function hi(i,t,e,n,s,r=null){Eu(i,s,r,t.mapping,e,n)}p(hi,"poseTubeBake");function xo(i){return!!i&&typeof i=="object"&&!Array.isArray(i)}p(xo,"isObject");var Pu=Math.PI/180;function _o(i){let t={};for(let[e,n]of Object.entries(xo(i)?i:{})){if(!xo(n)||typeof n.update!="function")continue;let s=Number(n.duration);t[String(e)]={id:String(e),label:String(n.label||e),duration:Number.isFinite(s)&&s>0?s:1,loop:n.loop!==!1,update:n.update}}return t}p(_o,"normalizeAnimationClips");function Lu(i){let t=new Map;for(let e of i?.parts||[]){let n=String(e.label||e.name||"").trim();n&&(t.has(n)||t.set(n,[]),t.get(n).push(String(e.id)))}return t}p(Lu,"partIdsByLabel");function Nu(i,t){let e=String(t).replace(/^#/,"").split(",").map(s=>s.trim()).filter(Boolean);if(!e.length||!e.every(s=>/^o[\d.]+$/.test(s)))return null;let n=[];for(let s of i?.parts||[]){let r=String(s.id);e.some(o=>r===o||r.startsWith(`${o}.`))&&n.push(r)}return n.length?n:null}p(Nu,"partIdsForOccurrenceRefs");function Du(i,t){let e=Lu(t),n=new Map,s=new Map,r=new Map;return{model:{get:p(c=>{let l=e.get(String(c).replace(/^#/,""))||e.get(String(c))||Nu(t,c);if(!l||!l.length){let f=[...e.keys()].sort().join(", ")||"(none)";throw new Error(`animation: no occurrence labeled ${JSON.stringify(c)}; labels: ${f}`)}let h=p(f=>{for(let d of l){let m=n.get(d);n.set(d,m?new i.Matrix4().multiplyMatrices(f,m):f.clone())}},"applyMatrix"),u=p((f,d)=>{for(let m of l){let g=s.get(m)||{};g[f]=d,s.set(m,g)}},"setStyle");return{deformTube(f){let d=mo(f);for(let m of l)r.set(m,d);return this},rotate(f,d,m=[0,0,0]){let g=new i.Vector3(f[0],f[1],f[2]).normalize(),_=new i.Matrix4().makeRotationAxis(g,(Number(d)||0)*Pu),x=new i.Matrix4().makeTranslation(-m[0],-m[1],-m[2]),M=new i.Matrix4().makeTranslation(m[0],m[1],m[2]);return h(new i.Matrix4().multiplyMatrices(M,new i.Matrix4().multiplyMatrices(_,x))),this},translate(f){return h(new i.Matrix4().makeTranslation(Number(f[0])||0,Number(f[1])||0,Number(f[2])||0)),this},opacity(f){return u("opacity",Math.max(0,Math.min(1,Number(f)))),this},visible(f){return u("visible",!!f),this}}},"handleFor"),labels:p(()=>[...e.keys()].sort(),"labels")},matrices:n,styles:s,deformations:r}}p(Du,"createAnimationFrame");function Is(i,t,e,n){let s=Du(i,t),r=e.duration||1,o=Math.max(0,Number(n)||0);return e.loop!==!1?o=o%r:o=Math.min(o,r),e.update(o,s.model),{matrices:s.matrices,styles:s.styles,deformations:s.deformations}}p(Is,"evaluateAnimationClip");function Uu(i){return String(i??"").trim()}p(Uu,"normalizeString");function Ps(i){return Math.max(Number(i?.duration)||0,.001)}p(Ps,"animationClipDuration");function yo(i){return!i||typeof i!="object"?[]:Object.values(i).filter(t=>t&&typeof t.update=="function").map(t=>({id:String(t.id),label:String(t.label||t.id),duration:Ps(t),loop:t.loop!==!1}))}p(yo,"animationClipList");function vo(i,t){let e=Uu(t);if(!e||!i||typeof i!="object")return null;let n=i[e];return n&&typeof n.update=="function"?n:null}p(vo,"findAnimationClip");var Mo=1,So=120,bo=7200;function Je(i){return`${Number(i.toFixed(3))}s`}p(Je,"formatSeconds");function Ao(i,t,{label:e="frame"}={}){let n=i&&typeof i=="object"?i:{},s=Number(n.fps??30);if(!Number.isInteger(s)||s<Mo||s>So)throw new Error(`${e} fps must be a whole number ${Mo}..${So}, got ${JSON.stringify(n.fps)}`);let r=n.start===void 0||n.start===null?0:Number(n.start);if(!Number.isFinite(r)||r<0)throw new Error(`${e} start must be seconds >= 0, got ${JSON.stringify(n.start)}`);let o=Ps(t);if(r>=o)throw new Error(`${e} start ${Je(r)} is at or past the end of a ${Je(o)} clip: every frame would be the same one`);let a=t?.loop!==!1,c=n.seconds===void 0||n.seconds===null?a?o:o-r:Number(n.seconds);if(!Number.isFinite(c)||c<=0)throw new Error(`${e} seconds must be a positive number, got ${JSON.stringify(n.seconds)}`);let l=Math.max(1,Math.round(c*s));if(l>bo)throw new Error(`${e} ${Je(c)} at ${s} fps schedules ${l} frames, past the ${bo}-frame ceiling`);let h=[];return!a&&r+c-o>1e-9&&h.push(`${e} covers ${Je(r)}..${Je(r+c)} of a ${Je(o)} clip that does not loop: every frame past its end is the same final pose`),{fps:s,seconds:c,start:r,frameCount:l,warnings:h}}p(Ao,"resolveFramePlan");function wo(i,t){return i.start+t/i.fps}p(wo,"framePlanElapsedSec");var Fu={Matrix4:mt,Vector3:k},Ls=Object.freeze(["opacity","visible"]),To=Object.freeze(["refuse","morph","rest"]),Ou=4,Bu=96;function zu(i){let t=Math.max(Ou,Math.ceil(Bu/i.fps));return{multiple:t,hz:i.fps*t,count:(i.frameCount-1)*t+1}}p(zu,"morphFitGrid");var ui=.001;function ku(){return new mt().set(ui,0,0,0,0,0,ui,0,0,-ui,0,0,0,0,0,1)}p(ku,"cadToGlbBasis");function Vu(){let i=1/ui;return new mt().set(i,0,0,0,0,0,-i,0,0,i,0,0,0,0,0,1)}p(Vu,"glbToCadBasis");var Gu=1e-12,Hu=new mt().elements;function Wu(i){let t=i.elements;for(let e=0;e<16;e+=1)if(Math.abs(t[e]-Hu[e])>Gu)return!1;return!0}p(Wu,"isIdentityMatrix");function Xu(i){let t=[];for(let e of i?.occurrences||[]){let n=String(e?.id||"").trim(),s=String(e?.component||"").trim(),r=n||s;if(!r)continue;let o=String(e?.name||n||s).trim();t.push({id:r,occurrenceId:r,componentId:s,name:o,label:o})}return{parts:t}}p(Xu,"animationTargetsFromDescriptor");function Ae(i,t=6){let e=[...i].sort();return e.length<=t?e.join(", "):`${e.slice(0,t).join(", ")} (and ${e.length-t} more)`}p(Ae,"summarize");function qu(i){let t={translations:[],rotations:[],scales:[],count:0};for(let e=0;e<i;e+=1)Ds(t,null);return t}p(qu,"newTrack");var Eo=new k,Co=new Ht,Ro=new k;function Ds(i,t){let e=0,n=0,s=0,r=0,o=0,a=0,c=1,l=1,h=1,u=1;if(t!==null&&(t.decompose(Eo,Co,Ro),{x:e,y:n,z:s}=Eo,{x:r,y:o,z:a,w:c}=Co,{x:l,y:h,z:u}=Ro),i.count>0){let f=(i.count-1)*4;i.rotations[f]*r+i.rotations[f+1]*o+i.rotations[f+2]*a+i.rotations[f+3]*c<0&&(r=-r,o=-o,a=-a,c=-c)}i.translations.push(e,n,s),i.rotations.push(r,o,a,c),i.scales.push(l,h,u),i.count+=1}p(Ds,"appendSample");function Ns(i,t,e){for(let n=1;n<e;n+=1)for(let s=0;s<t;s+=1)if(Math.fround(i[n*t+s])!==Math.fround(i[s]))return!0;return!1}p(Ns,"varies");function $u(i,t){for(let e=0;e<t*3;e+=1)if(Math.fround(i[e])!==1)return!1;return!0}p($u,"scaleIsUnit");function Io(i,t,e,{drop:n=[],deform:s="refuse"}={}){let r=new Set(n.map(T=>String(T).trim())),o=[...r].filter(T=>!Ls.includes(T));if(o.length)throw new Error(`animation drop names ${o.sort().join(", ")}, which is not an effect this export can bake static; droppable effects: ${Ls.join(", ")}`);let a=String(s||"refuse");if(!To.includes(a))throw new Error(`animation deform must be one of ${To.join(", ")}, got ${JSON.stringify(s)}`);let c=Xu(i),l=ku(),h=Vu(),u=new mt,f=new Map,d=new Map,m=new Set,g=new Set,_=new Set,x=new Set,M=new Map,y=new Set,v=a==="morph"?zu(e):{multiple:1,hz:e.fps,count:e.frameCount};for(let T=0;T<v.count;T+=1){let D=wo(e,T/v.multiple),L=Is(Fu,c,t,D),P=T%v.multiple===0?T/v.multiple:-1;if(P>=0){for(let[R,I]of L.matrices){let E=f.get(R);if(!E){if(Wu(I))continue;E=qu(P),f.set(R,E)}u.multiplyMatrices(l,I).multiply(h),Ds(E,u)}for(let R of f.values())R.count===P&&Ds(R,null);for(let[R,I]of L.styles)I&&Object.hasOwn(I,"opacity")&&(g.add(R),P===0&&d.set(R,I.opacity)),I&&Object.hasOwn(I,"visible")&&(_.add(R),P===0&&I.visible===!1&&m.add(R))}for(let[R,I]of L.deformations){if(x.add(R),I.braid&&y.add(R),a!=="morph")continue;let E=M.get(R);if(!E)E={rest:I,samples:[]},M.set(R,E);else if(!po(E.rest,I))throw new Error(`clip ${t.id} changes the REST path of ${R} at ${D.toFixed(4)}s, so its geometry has no single base mesh for morph targets to be deltas against. Author one rest path per tube for the whole clip (move the tube with .translate/.rotate instead), or export the clip as video (cadgen step snapshot --animation ${t.id} --video)`);E.samples.push({index:T,timeSec:T/v.hz,deformation:I===E.rest?I:{...I,restSpec:E.rest.restSpec}})}}let b=[];for(let T of Ls){let D=T==="opacity"?g:_;if(D.size){if(!r.has(T))throw new Error(`clip ${t.id} animates .${T}() on ${Ae(D)}, and glTF has no standard animated channel for it. Pass drop: ["${T}"] to bake the value at start into the file instead, or animate the occurrence's transform rather than its appearance`);b.push(`.${T}() is not an animated glTF channel: ${Ae(D)} carries its value at start, frozen for the whole clip`)}}if(x.size){if(a==="refuse")throw new Error(`clip ${t.id} deforms tube geometry on ${Ae(x)}: that is per-vertex motion, which a node transform cannot carry. Pass deform: "morph" to bake it as morph targets (bigger file, deformTolerance sets how close they track), deform: "rest" to ship those tubes at their rest shape knowing they do not move, or export the clip as video (cadgen step snapshot --animation ${t.id} --video)`);a==="morph"?(y.size&&b.push(`${Ae(y)} carries a braid: the strand pattern is a shader, not geometry, so the exported cord has the right shape and motion and a smooth surface`),b.push("morph targets carry the tube deformation as per-vertex keyframes; cadgen's own CAD Viewer reads a GLB's geometry and ignores its glTF animation, so play this file in Blender, a three.js viewer or a browser model preview")):b.push(`deform: "rest" ships ${Ae(x)} at rest shape: the clip's tube deformation is per-vertex motion this file does not carry`)}let A=[...m].filter(T=>f.has(T));if(A.length){for(let T of A)f.delete(T);b.push(`${Ae(A)} moves in this clip and is hidden at start: dropping .visible() omits the occurrence from the file, and a node that is not there carries no motion`)}let w=new Float32Array(e.frameCount);for(let T=0;T<e.frameCount;T+=1)w[T]=T/e.fps;let S=[],C=new Map;for(let[T,D]of f){let L=new Float32Array(D.translations),P=new Float32Array(D.rotations),R=new Float32Array(D.scales),I=$u(R,D.count);C.set(T,{translation:[L[0],L[1],L[2]],rotation:[P[0],P[1],P[2],P[3]],scale:I?null:[R[0],R[1],R[2]]});let E={node:T};Ns(L,3,D.count)&&(E.translation=L),Ns(P,4,D.count)&&(E.rotation=P),!I&&Ns(R,3,D.count)&&(E.scale=R),(E.translation||E.rotation||E.scale)&&S.push(E)}return S.sort(Po),{name:t.id,times:w,channels:S,rest:C,statics:{opacity:d,hidden:m},deformations:M,grid:v,warnings:b}}p(Io,"sampleClipAnimation");function Po(i,t){return i.node!==t.node?i.node<t.node?-1:1:(i.weights?1:0)-(t.weights?1:0)}p(Po,"compareChannels");function Lo(i,t){return t?.length?{...i,channels:[...i.channels,...t].sort(Po)}:i}p(Lo,"withMorphChannels");function No(i,t){let e=i.channels.map(s=>s.node).filter(s=>!t.has(s));if(!e.length)return i;let n=new Map;for(let[s,r]of i.rest)t.has(s)&&n.set(s,r);return{...i,channels:i.channels.filter(s=>t.has(s.node)),rest:n,warnings:[...i.warnings,`${Ae(e)} moves in this clip but has no geometry in the export, so the file carries no node to animate for it`]}}p(No,"restrictAnimationToNodes");var fi={BufferGeometry:ze,Float32BufferAttribute:se,Matrix3:Y,Vector3:k},Yu=1,Us=512*1024*1024,Do=16,Uo=5,Zu=128,Ju=512,di=new mt;function Fo(i,t=6){let e=[...i].sort();return e.length<=t?e.join(", "):`${e.slice(0,t).join(", ")} (and ${e.length-t} more)`}p(Fo,"summarize");function Oo(i){return i>=1024**3?`${(i/1024**3).toFixed(2)} GiB`:`${(i/1024**2).toFixed(1)} MiB`}p(Oo,"formatBytes");function Ku(i,t){let e=Array.isArray(i.transform)?i.transform:null,n=e===null||ws(e),s=!n&&bs(e)<0,r=n?null:As(e),o=t.positions,a=t.normals,c=Math.floor(o.length/3),l=new Float32Array(o.length),h=new Float32Array(o.length);for(let M=0;M<c;M+=1){let y=M*3;n?(l[y]=o[y],l[y+1]=o[y+1],l[y+2]=o[y+2]):Ss(e,o[y],o[y+1],o[y+2],l,y);let v=a[y],b=a[y+1],A=a[y+2],w=v,S=b,C=A;r&&(w=r[0]*v+r[1]*b+r[2]*A,S=r[3]*v+r[4]*b+r[5]*A,C=r[6]*v+r[7]*b+r[8]*A);let T=Math.hypot(w,S,C)||1;h[y]=w/T,h[y+1]=S/T,h[y+2]=C/T}let u=t.faceRanges||[],f=0;for(let M of u)f+=Math.floor((Number(M.indexCount)||0)/3);let d=new Uint32Array(f*3),m=new Uint32Array(f),g=s?[0,2,1]:[0,1,2],_=0;u.forEach((M,y)=>{let v=Number(M.indexStart)||0,b=Number(M.indexCount)||0;for(let A=v;A+2<v+b;A+=3)d[_*3]=t.indices[A+g[0]],d[_*3+1]=t.indices[A+g[1]],d[_*3+2]=t.indices[A+g[2]],m[_]=y,_+=1});let x=new ze;return x.setAttribute("position",new It(l,3)),x.setAttribute("normal",new It(h,3)),x.setIndex(new It(d,1)),{geometry:x,triangleRange:m}}p(Ku,"occurrenceWorldGeometry");function ju(i){let t=i.values,e=Math.floor(t.length/8),n=new Map;for(let a=0;a<e;a+=1){let c=a*8,l=t[c],h=n.get(l);if(!h){n.set(l,[t[c+1],t[c+1],t[c+2],t[c+2],t[c+3],t[c+3]]);continue}for(let u=0;u<3;u+=1){let f=t[c+1+u];f<h[u*2]&&(h[u*2]=f),f>h[u*2+1]&&(h[u*2+1]=f)}}let s=[...n.keys()].sort((a,c)=>a-c),r=new Uint32Array(s.length+1),o=[];return s.forEach((a,c)=>{let l=n.get(a),h=[0,1,2].map(u=>l[u*2]===l[u*2+1]?[l[u*2]]:[l[u*2],l[u*2+1]]);for(let u of h[0])for(let f of h[1])for(let d of h[2])o.push(u,f,d);r[c+1]=o.length/3}),{fractions:Float64Array.from(s),cornerOffset:r,uva:Float64Array.from(o)}}p(ju,"boundsForFractions");function Bo(i,t,e){let n=t.path,s=(t.twistDeg||0)*Math.PI/180,r=Math.cos(s),o=Math.sin(s);for(let a=0;a<i.fractions.length;a+=1){let c=ci(n,i.fractions[a]*n.length),l=c.point,h=c.normal,u=c.binormal,f=c.tangent;for(let d=i.cornerOffset[a];d<i.cornerOffset[a+1];d+=1){let m=d*3,g=i.uva[m],_=i.uva[m+1],x=i.uva[m+2],M=r*g-o*_,y=o*g+r*_;e[m]=l[0]+h[0]*M+u[0]*y+f[0]*x,e[m+1]=l[1]+h[1]*M+u[1]*y+f[1]*x,e[m+2]=l[2]+h[2]*M+u[2]*y+f[2]*x}}return e}p(Bo,"poseCorners");function Qu(i,t,e,n){let s=0;for(let r=0;r<e.length;r+=3){let o=e[r]-(i[r]+(t[r]-i[r])*n),a=e[r+1]-(i[r+1]+(t[r+1]-i[r+1])*n),c=e[r+2]-(i[r+2]+(t[r+2]-i[r+2])*n),l=o*o+a*a+c*c;l>s&&(s=l)}return Math.sqrt(s)}p(Qu,"blendDeviation");function tf(i,t,e){let n=i.length,s=[0];if(n<2)return s;let r=0,o=Bo(t,be(i[0]),new Float64Array(t.uva.length)),a=o,c=[],l=!0;for(let h=1;h<n;h+=1){let u=li(i[h],i[h-1])?a:Bo(t,be(i[h]),new Float64Array(t.uva.length));a=u,c.push({index:h,pose:u}),l=l&&li(i[h],i[r]);let f=!1;if(!l){let g=h-r;for(let _ of c){if(_.index===h)continue;let x=(_.index-r)/g;if(Qu(o,u,_.pose,x)>e){f=!0;break}}}if(!f&&c.length<Zu)continue;let d=f?h-1:h,m=c.find(g=>g.index===d);s.push(d),r=d,o=m.pose,c=c.filter(g=>g.index>d),l=c.every(g=>li(i[g.index],i[r]))}return s[s.length-1]!==n-1&&s.push(n-1),s}p(tf,"fitTargetTimes");function ef(i,t,e){let n=i.geometry.index,s=Math.floor(n.count/3),r=i.sourceTriangles,o=new Map;for(let a=0;a<s;a+=1){let c=r?r[a]:a,l=e[t[c]]||e[0],h=o.get(l);h||o.set(l,h=[]),h.push(a)}return[...o.entries()].map(([a,c])=>{let l=new Uint32Array(c.length*3),h=new Map,u=0;c.forEach((d,m)=>{for(let g=0;g<3;g+=1){let _=n.getX(d*3+g),x=h.get(_);x===void 0&&(x=u,u+=1,h.set(_,x)),l[m*3+g]=x}});let f=new Uint32Array(u);for(let[d,m]of h)f[m]=d;return{color:a,indices:l,vertexIds:f,slotOf:h}})}p(ef,"partitionByColor");function Sn(i,t){let e=new Float32Array(t.length*3);for(let n=0;n<t.length;n+=1){let s=t[n]*3;e[n*3]=i[s],e[n*3+1]=i[s+1],e[n*3+2]=i[s+2]}return e}p(Sn,"gather");function nf(i){let t=Math.max(1,Math.min(i,Ju)),e=new Uint32Array(t);for(let n=0;n<t;n+=1)e[n]=Math.floor(n*i/t);return e}p(nf,"verifySampleIds");function sf(i,t){let e=0;for(let n=0;n<i.length;n+=3){let s=i[n],r=i[n+1],o=i[n+2],a=t[n],c=t[n+1],l=t[n+2],h=Math.hypot(s,r,o)*Math.hypot(a,c,l);if(h<1e-12)continue;let u=Math.min(1,Math.max(-1,(s*a+r*c+o*l)/h)),f=Math.acos(u)*180/Math.PI;f>e&&(e=f)}return e}p(sf,"maxNormalDegrees");function zo(i,t,e,n={}){let{toleranceMm:s=Yu,grid:r,defaultColor:o=null,clipId:a="clip",maxRuntimeBytes:c=Us}=n,l=Number(s);if(!(l>0))throw new Error(`morph deformTolerance must be a positive number of millimetres, got ${s}`);let h=[],u=new Map,f=[];if(!e?.size)return{overrides:u,channels:f,warnings:h,stats:null};let d=[],m=[];for(let M of i.occurrences||[]){let y=String(M.component||""),v=String(M.id||y),b=e.get(v);if(!b)continue;let A=t.get(y);if(!A||!A.positions?.length){m.push(v);continue}d.push({occurrence:M,occurrenceId:v,tessellation:A,entry:b})}if(m.length&&h.push(`${Fo(m)} deforms in this clip but tessellated to nothing, so the file carries no geometry to morph for it`),!d.length)return{overrides:u,channels:f,warnings:h,stats:null};let g=[],_=0;for(let M of d){let y=M.entry.samples[0].deformation,{geometry:v,triangleRange:b}=Ku(M.occurrence,M.tessellation),A=go(fi,v,be(y),di),w={restSpec:y.restSpec,pathSpec:y.restSpec,twistDeg:0,maxSegmentLength:y.maxSegmentLength,braid:y.braid},S=new Array(r.count).fill(w);for(let L of M.entry.samples)S[L.index]=L.deformation;let C=ju(A.mapping),T=tf(S,C,l),D=A.vertexCount;g.push({...M,bake:A,model:C,poses:S,keys:T,triangleRange:b,vertexCount:D}),_+=D*Math.max(0,T.length-1)*2*Do}if(_>Math.min(c,Us)){let M=g.reduce((v,b)=>v+Math.max(0,b.keys.length-1),0),y=g.reduce((v,b)=>v+b.vertexCount,0);throw new Error(`clip ${a} needs ${M} morph targets over ${g.length} tubes (${y} refined vertices) to hold ${l}mm, which is ${Oo(_)} of morph texture at playback \u2014 past the ${Oo(Math.min(c,Us))} ceiling, and it is the GPU number rather than the file size that decides whether the file opens. Raise deformTolerance (the target count falls as its square root), shorten seconds, coarsen --mesh-tolerance so the tubes carry fewer vertices, or coarsen the clip's own maxSegmentLength`)}let x={toleranceMm:l,nodes:0,targets:0,bytes:0,runtimeBytes:0,refinedTriangles:0,deviationMm:0,normalsOmitted:[]};for(let M of g){let{bake:y,poses:v,keys:b,vertexCount:A,occurrenceId:w}=M,S=new se(new Float32Array(A*3),3),C=new se(new Float32Array(A*3),3);hi(fi,y,be(v[b[0]]),di,S,C);let T=Float32Array.from(S.array),D=Float32Array.from(C.array),L=nf(A),P=[],R=[],I=[],E=0;for(let G=1;G<b.length;G+=1){hi(fi,y,be(v[b[G]]),di,S,C);let X=new Float32Array(A*3),q=new Float32Array(A*3);for(let $=0;$<X.length;$+=1)X[$]=S.array[$]-T[$],q[$]=C.array[$]-D[$];P.push(X),R.push(q),I.push(Sn(S.array,L)),E=Math.max(E,sf(D,C.array))}let F=E>=Uo;!F&&P.length&&x.normalsOmitted.push(w);let O=new Int32Array(b.length).fill(-1),N=[];for(let G=1;G<b.length;G+=1){let X=P[G-1],q=!1;for(let $=0;$<X.length;$+=1)if(X[$]!==0){q=!0;break}q&&(O[G]=N.length,N.push(G-1))}let U=rf(M,{basePositions:T,deltaPositions:P,grid:r,tolerance:l,posed:S,posedNormals:C});x.deviationMm=Math.max(x.deviationMm,U);let z=to(i,M.occurrence,M.tessellation,o||void 0),B=Ms(M.occurrence.material),W=ef(y,M.triangleRange,z).map(G=>{let X=G.vertexIds,q=N.map(Q=>({positionDeltas:Sn(P[Q],X),...F?{normalDeltas:Sn(R[Q],X)}:{}})),$=[],K=[];return L.forEach((Q,j)=>{let ct=G.slotOf.get(Q);ct!==void 0&&($.push(ct),K.push(j))}),{color:G.color,positions:Sn(T,X),normals:Sn(D,X),indices:G.indices,...B===null?{}:{material:B},...q.length?{targets:q}:{},...q.length&&$.length?{verify:{vertexIds:Uint32Array.from($),posed:N.map(Q=>{let j=I[Q],ct=new Float32Array(K.length*3);return K.forEach((qt,xt)=>{ct[xt*3]=j[qt*3],ct[xt*3+1]=j[qt*3+1],ct[xt*3+2]=j[qt*3+2]}),ct})}}:{}}});u.set(w,W),x.nodes+=1,x.targets+=N.length,x.refinedTriangles+=Math.floor(y.geometry.index.count/3);for(let G of W){let X=G.positions.length/3;x.bytes+=X*N.length*(F?24:12),x.runtimeBytes+=X*N.length*(F?2:1)*Do}if(N.length){let G=new Float32Array(b.length),X=new Float32Array(b.length*N.length);for(let q=0;q<b.length;q+=1)G[q]=b[q]/r.hz,O[q]>=0&&(X[q*N.length+O[q]]=1);f.push({node:w,times:G,weights:X,targetCount:N.length})}}return x.normalsOmitted.length&&h.push(`${Fo(x.normalsOmitted)} turns by less than ${Uo}\xB0 over this clip, so its morph targets carry positions only and its shading rides the base normals`),{overrides:u,channels:f,warnings:h,stats:x}}p(zo,"buildTubeMorphTargets");function rf(i,{basePositions:t,deltaPositions:e,grid:n,tolerance:s,posed:r,posedNormals:o}){let{bake:a,poses:c,keys:l,occurrenceId:h}=i;if(l.length<2)return 0;let u=0,f=0;for(let d=0;d<c.length;d+=n.multiple){for(;f+2<l.length&&l[f+1]<=d;)f+=1;let m=l[f],g=l[f+1],_=g===m?0:(d-m)/(g-m);hi(fi,a,be(c[d]),di,r,o);let x=f>=1?e[f-1]:null,M=e[f];for(let y=0;y<t.length;y+=3){let v=0;for(let b=0;b<3;b+=1){let A=t[y+b]+(x?x[y+b]*(1-_):0)+(M?M[y+b]*_:0),w=r.array[y+b]-A;v+=w*w}v>u&&(u=v)}}if(u=Math.sqrt(u),u>s+.001)throw new Error(`morph fit for ${h} leaves ${u.toFixed(4)}mm between the baked targets and the clip's own deformation, past the ${s}mm it was fitted to`);return u}p(rf,"verifyMorphFit");var Fs=Object.freeze(["clips"]);function of(i){if(typeof Buffer<"u")return Buffer.from(i,"utf8").toString("base64");let t=new TextEncoder().encode(i),e="";for(let n of t)e+=String.fromCharCode(n);return btoa(e)}p(of,"base64Utf8");async function ko(i,{name:t="render module"}={}){let e=String(i||""),n=`data:text/javascript;base64,${of(e)}`;try{return await import(n)}catch(s){let r=s instanceof Error?s.message:String(s);throw new Error(`${t}: ${r}`)}}p(ko,"importRenderModule");function Vo(i,{name:t="render module"}={}){let n=Object.keys(i||{}).filter(r=>r!=="default").filter(r=>!Fs.includes(r));if(n.length)throw new Error(`${t}: unknown export${n.length===1?"":"s"} ${n.join(", ")} \u2014 the renderer understands: ${Fs.join(", ")}`);if("default"in(i||{}))throw new Error(`${t}: a default export is not a render-module export \u2014 use named exports (${Fs.join(", ")})`);return{clips:_o(i?.clips)}}p(Vo,"compileRenderModule");function af(i){let t={},e=[],n=[],s=[],r=[],o={chord:void 0,angle:void 0};for(let a=0;a<i.length;a+=1){let c=i[a];if(!c.startsWith("--"))continue;let l=i[a+1],h=l===void 0||l.startsWith("--")?"true":l;h!=="true"&&(a+=1),c==="--format"?(e.push(h),s.push({chord:void 0,angle:void 0}),r.push(void 0)):c==="--out"?n.push(h):c==="--chord-tolerance"?(s.length?s[s.length-1]:o).chord=h:c==="--angle-tolerance"?(s.length?s[s.length-1]:o).angle=h:c==="--animation"?(r.length||Et("--animation must follow the --format/--out pair it animates"),r[r.length-1]=h):t[c.slice(2)]=h}return{args:t,formats:e,outs:n,pairTolerances:s,pairAnimations:r,defaults:o}}p(af,"parseArgs");function Et(i){process.stdout.write(`${JSON.stringify({ok:!1,error:String(i)})}
`),process.exit(1)}p(Et,"fail");function cf(i,t,e,n){let s=Lr(t,n),r=Ur(Br(s));if(r)return{...r.component,partColor:r.partColor};let o=String(e?.surf||"");if(!o)throw new Error(`component ${t} has no surf payload`);let a=Ke.readFileSync(we.join(i,o)),{index:c,floats:l}=ks(a.buffer.slice(a.byteOffset,a.byteOffset+a.byteLength)),h=fs(c,l,n),u=Array.isArray(c.partColor)?c.partColor:null;return zr(s,Dr(h,{partColor:u,edgeClasses:Nr(c)})),{...h,partColor:u}}p(cf,"tessellationForComponent");var{args:bn,formats:Os,outs:Xo,pairTolerances:Go,pairAnimations:Ho,defaults:Wo}=af(process.argv.slice(2)),pi=String(bn["package-dir"]||"");(!pi||!we.isAbsolute(pi))&&Et("--package-dir must be an absolute render-package directory");(!Os.length||Os.length!==Xo.length)&&Et("--format and --out must be given as one or more ordered pairs");var Te=Os.map((i,t)=>{let e=Go[t].chord??Wo.chord,n=Go[t].angle??Wo.angle,s={...Bt};e!==void 0&&(s.chordTolerance=Number(e)),n!==void 0&&(s.angleTolerance=Number(n));let r=null;if(Ho[t]!==void 0){try{r=JSON.parse(String(Ho[t]))}catch(o){Et(`--animation must be a JSON object: ${o?.message||o}`)}(!r||typeof r!="object"||Array.isArray(r))&&Et("--animation must be a JSON object")}return{format:String(i).toLowerCase(),out:String(Xo[t]),options:s,animation:r,groupKey:`${s.chordTolerance}:${s.angleTolerance}`}});for(let i of Te)(!i.out||!we.isAbsolute(i.out))&&Et("--out must be an absolute output path"),vs.includes(i.format)||Et(`--format must be one of ${vs.join(", ")}`),(!(i.options.chordTolerance>0)||!(i.options.angleTolerance>0))&&Et("tolerances must be positive numbers"),i.animation&&i.format!=="glb"&&Et(`${i.format} carries no animation: only glb does`),i.animation&&!String(i.animation.clip||"").trim()&&Et("--animation must name a clip");new Set(Te.map(i=>i.out)).size!==Te.length&&Et("--out paths must be distinct");var lf=String(bn.name||we.basename(Te[0].out).replace(/\.[^.]+$/,"")||"model"),mi=bn["default-color"]?String(bn["default-color"]):null;mi!==null&&!/^#[0-9a-fA-F]{6}$/.test(mi)&&Et("--default-color must be #rrggbb");var qo=String(bn["render-module"]||"");Te.some(i=>i.animation)&&!qo&&Et("--animation needs --render-module: the clips live in the .step.js beside the document");async function hf(i){let t=Ke.readFileSync(i,"utf8"),e=we.basename(i),n=await ko(t,{name:e});return Vo(n,{name:e}).clips}p(hf,"loadClips");function uf(i,t,e){let n=String(i.animation.clip),s=vo(t,n);if(!s){let a=yo(t).map(c=>c.id);throw new Error(a.length?`Unknown animation clip: ${n}. This model declares: ${a.join(", ")}`:`Unknown animation clip: ${n}. This model declares no animation clips`)}let r=Ao(i.animation,s,{label:"animation"}),o=Io(e,s,r,{drop:Array.isArray(i.animation.drop)?i.animation.drop:[],deform:i.animation.deform});return{clip:s,plan:r,sampled:o}}p(uf,"sampleJobAnimation");try{let i=JSON.parse(Ke.readFileSync(we.join(pi,"assembly.json"),"utf8")),t=i.components||{},e=new Set((i.occurrences||[]).map(o=>String(o.component||""))),n=Te.some(o=>o.animation)?await hf(qo):null,s=new Map;Te.forEach((o,a)=>{s.has(o.groupKey)||s.set(o.groupKey,{options:o.options,members:[]}),s.get(o.groupKey).members.push({job:o,index:a})});let r=[];for(let o of s.values()){let a=new Map;for(let h of e){if(!t[h])throw new Error(`descriptor names unknown component ${h}`);a.set(h,cf(pi,h,t[h],o.options))}let c=mi?{defaultColor:mi.toLowerCase()}:{},l=null;for(let{job:h,index:u}of o.members){let f,d=null,m=null;if(h.animation){let{plan:x,sampled:M}=uf(h,n,i),y=zo(i,a,M.deformations,{toleranceMm:h.animation.deformTolerance,grid:M.grid,clipId:M.name,...c.defaultColor?{defaultColor:c.defaultColor}:{}});f=Ts(i,a,{...c,perOccurrence:!0,hiddenOccurrenceIds:M.statics.hidden,occurrenceOpacity:M.statics.opacity,occurrenceOverrides:y.overrides}),d=No(Lo(M,y.channels),new Set(f.primitives.map(v=>v.node).filter(Boolean))),m={clip:d.name,fps:x.fps,samples:x.frameCount,seconds:x.seconds,start:x.start,channels:d.channels.length,...y.stats?{deform:{mode:"morph",nodes:y.stats.nodes,targets:y.stats.targets,bytes:y.stats.bytes,runtimeBytes:y.stats.runtimeBytes,refinedTriangles:y.stats.refinedTriangles,deviationMm:Number(y.stats.deviationMm.toFixed(4)),toleranceMm:y.stats.toleranceMm,fitGridHz:M.grid.hz}}:{},warnings:[...x.warnings,...d.warnings,...y.warnings]}}else l=l||Ts(i,a,c),f=l;if(!f.triangleCount)throw new Error("tree produced no triangles");let{body:g}=eo(f,h.format,{name:lf,animation:d});Ke.mkdirSync(we.dirname(h.out),{recursive:!0});let _=`${h.out}.${process.pid}.tmp`;Ke.writeFileSync(_,g),Ke.renameSync(_,h.out),r[u]={path:h.out,format:h.format,triangleCount:f.triangleCount,...m?{animation:m}:{}}}}process.stdout.write(`${JSON.stringify({ok:!0,files:r})}
`)}catch(i){Et(i?.message||i)}
/*! Bundled license information:

three/build/three.core.js:
three/build/three.module.js:
  (**
   * @license
   * Copyright 2010-2026 Three.js Authors
   * SPDX-License-Identifier: MIT
   *)
*/
