import logoUrl from "../../assets/logo-c.svg";

/** The C brand mark remains visible while a file loads. */
export default function ViewerBrand() {
  return <img src={logoUrl} alt="CAD" width={20} height={20} className="mr-1 size-5 shrink-0 object-contain" />;
}
