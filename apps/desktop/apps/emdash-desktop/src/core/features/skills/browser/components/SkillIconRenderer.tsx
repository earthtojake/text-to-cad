import type { CatalogSkill } from '@emdash/core/primitives/skills/api';
import React, { useState } from 'react';
import { useTheme } from '@core/primitives/theme/browser';
import { resolveSkillIcon } from './skillIcons';

function processSvg(raw: string, fillColor: string): string {
  let svg = raw.replace(/\bwidth="[^"]*"/g, '').replace(/\bheight="[^"]*"/g, '');
  svg = svg.replace('<svg ', `<svg fill="${fillColor}" `);
  return svg.replace('<svg ', '<svg class="h-full w-full" ');
}

interface SkillIconRendererProps {
  skill: CatalogSkill;
}

export const SkillIconRenderer: React.FC<SkillIconRendererProps> = ({ skill }) => {
  const [imgError, setImgError] = useState(false);
  const { effectiveTheme } = useTheme();
  const isDark = effectiveTheme === 'emdark';

  const letter = skill.displayName.charAt(0).toUpperCase();

  const renderImageIcon = () => {
    if (!skill.iconUrl || imgError) return null;
    const filter =
      skill.source === 'skillssh'
        ? undefined
        : isDark
          ? 'brightness(0) invert(1)'
          : 'brightness(0)';
    return (
      <img
        src={skill.iconUrl}
        alt=""
        className="h-full w-full rounded-lg object-contain"
        style={{ filter }}
        onError={() => setImgError(true)}
        loading="lazy"
      />
    );
  };

  const renderIcon = () => {
    if (skill.source === 'skillssh') {
      const imageIcon = renderImageIcon();
      if (imageIcon) return imageIcon;
    }

    const svg = resolveSkillIcon(skill.catalogSkillId ?? skill.id, skill.source);
    if (svg) {
      const html = processSvg(svg, isDark ? '#ffffff' : '#000000');
      return <div dangerouslySetInnerHTML={{ __html: html }} />;
    }

    return renderImageIcon() ?? letter;
  };

  return (
    <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-background-2 p-2 font-semibold text-foreground/60 transition-colors group-hover:bg-background-3">
      {renderIcon()}
    </div>
  );
};
