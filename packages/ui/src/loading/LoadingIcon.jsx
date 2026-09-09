import { createElement, useEffect, useState } from "react";
import animation from "../assets/hardcore-loading.webp";
import still from "../assets/hardcore-still.webp";

/** Decorative: the surrounding loading status owns the accessible announcement. */
export default function LoadingIcon({ active = true, size = 96, className = "" }) {
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

  // Keep this tiny public entry usable without the CAD surface's JSX transform.
  return createElement("img", {
    src: active && animate && !failed ? animation : still,
    alt: "",
    "aria-hidden": true,
    width: size,
    height: size,
    draggable: false,
    className: `shrink-0 select-none object-contain ${className}`,
    "data-loading-icon": "",
    onError: () => setFailed(true),
  });
}
