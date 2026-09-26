import { createElement, useEffect, useState } from "react";
import animation from "../assets/hardcore-loading.webp";
import still from "../assets/hardcore-still.webp";

/**
 * Decorative: the surrounding loading status owns the accessible announcement. It animates
 * unless the system asks for reduced motion, the page is hidden, or the host passes
 * `reducedMotion` (an app's own motion setting).
 */
export default function LoadingIcon({ active = true, size = 96, className = "", reducedMotion = false }) {
  const [animate, setAnimate] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setAnimate(!motion.matches && !document.hidden);
    motion.addEventListener("change", update);
    document.addEventListener("visibilitychange", update);
    update();
    return () => {
      motion.removeEventListener("change", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, []);

  // Keep this tiny public entry usable without the CAD surface's JSX transform.
  return createElement("img", {
    src: active && animate && !reducedMotion && !failed ? animation : still,
    alt: "",
    "aria-hidden": true,
    width: size,
    height: size,
    draggable: false,
    className: `shrink-0 select-none object-contain ${className}`,
    onError: () => setFailed(true),
  });
}
