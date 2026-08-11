var e=Object.defineProperty;var n=(t,i)=>e(t,"name",{value:i,configurable:!0});import r from"node:fs";import{fileURLToPath as f}from"node:url";var o="";async function h(t){o=String(t?.logPath||"")}n(h,"initialize");async function s(t,i,a){if(o&&t.startsWith("file:"))try{r.appendFileSync(o,`${f(t)}
`)}catch{}return a(t,i)}n(s,"load");export{h as initialize,s as load};
