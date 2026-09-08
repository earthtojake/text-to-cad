import { useEffect, useState } from "react";
import animation from "@/assets/brand/hardcore-loading.webp";
import still from "@/assets/brand/hardcore-still.webp";

/** Decorative: the surrounding loading status owns the accessible announcement. */
export default function LoadingIcon() {
  const [animate, setAnimate] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setAnimate(
      !motion.matches && !document.hidden &&
      !document.documentElement.classList.contains("reduce-motion")
    );
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    motion.addEventListener("change", update);
    document.addEventListener("visibilitychange", update);
    update();
    return () => {
      observer.disconnect();
      motion.removeEventListener("change", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, []);

  return (
    <img
      src={animate && !failed ? animation : still}
      alt=""
      aria-hidden="true"
      width="96"
      height="96"
      draggable="false"
      className="mx-auto mb-3 h-24 w-24 select-none object-contain"
      onError={() => setFailed(true)}
    />
  );
}
