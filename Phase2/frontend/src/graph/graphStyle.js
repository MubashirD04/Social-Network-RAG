// Visual rules shared by the 2D and 3D renderers, so the two views can't
// disagree about what a node or edge means.
export const COLORS = {
  chat: '#FF6B6B',
  person: '#4ECDC4',
  topic: '#FFD93D',
  message: '#A0D2EB',
  bg: '#0f1115'
};

// Distinct hues cycled by community id so each cluster reads as its own
// color both on person nodes and on the edges between members of that
// cluster. -1 ("no community", e.g. isolated participants) falls back to
// a neutral gray rather than claiming a palette slot.
// Yellow is reserved for topic nodes and confirmed replies, so it's
// deliberately left out here: a community swatch never reads as "this is a
// topic".
export const COMMUNITY_PALETTE = [
  '#FF6B6B', '#4ECDC4', '#F4A261', '#A78BFA', '#F97316',
  '#22D3EE', '#F472B6', '#84CC16', '#60A5FA', '#FB923C',
  '#34D399', '#E879F9'
];
const NO_COMMUNITY_COLOR = '#6B7280';
const CONFIRMED_REPLY_COLOR = '#FFD93D';
const INFERRED_COLOR = '#A0B4C8';
const NEUTRAL_LINK_COLOR = '#FFFFFF';

export const communityColor = (communityId) => {
  if (communityId === undefined || communityId === null || communityId === -1) {
    return NO_COMMUNITY_COLOR;
  }
  return COMMUNITY_PALETTE[communityId % COMMUNITY_PALETTE.length];
};

export const nodeColor = (node) => (
  node.type === 'person' ? communityColor(node.community) : (COLORS[node.type] || '#fff')
);

const MIN_PERSON_RADIUS = 4;
const MAX_PERSON_RADIUS = 14;

// Person area scales with PageRank relative to the most influential person
// in this chat. Message nodes shrink with reply depth, so a nested thread
// reads visually as narrowing rather than a flat chain of identical dots.
export const nodeRadius = (node, maxPagerank) => {
  if (node.type === 'person') {
    const share = maxPagerank > 0 ? (node.pagerank || 0) / maxPagerank : 0;
    return MIN_PERSON_RADIUS + (MAX_PERSON_RADIUS - MIN_PERSON_RADIUS) * Math.sqrt(share);
  }
  if (node.type === 'message') return Math.max(2.5, 5 - (node.reply_depth || 0) * 0.6);
  return 6;
};

const isConfirmedReply = (link) => link.relationship === 'REPLIED_TO' && !link.inferred;

const sharedCommunity = (link) => {
  const { source, target } = link;
  if (source?.type !== 'person' || target?.type !== 'person') return null;
  if (source.community === undefined || source.community === null || source.community === -1) return null;
  return source.community === target.community ? source.community : null;
};

// Inferred edges keep their own color and dash even while highlighted, so a
// confirmed reply never looks like the same fact as a guess based on shared
// wording. The idle opacity keeps them at 3:1 contrast against the background.
export const linkStyle = (link, highlight) => {
  if (highlight && !highlight.linkIds.has(link.id)) {
    return { color: link.inferred ? INFERRED_COLOR : NEUTRAL_LINK_COLOR, opacity: 0.04, width: 0.5 };
  }
  if (link.inferred) return { color: INFERRED_COLOR, opacity: highlight ? 0.9 : 0.5, width: highlight ? 2 : 1 };
  if (highlight) return { color: CONFIRMED_REPLY_COLOR, opacity: 1, width: 2 };
  if (isConfirmedReply(link)) return { color: CONFIRMED_REPLY_COLOR, opacity: 0.85, width: 1.5 };
  const community = sharedCommunity(link);
  if (community !== null) return { color: communityColor(community), opacity: 0.8, width: 1 };
  return { color: NEUTRAL_LINK_COLOR, opacity: 0.25, width: 1 };
};

export const toRgba = (hex, opacity) => {
  const value = parseInt(hex.slice(1), 16);
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${opacity})`;
};

// WCAG contrast of a color at some opacity over the graph background.
export const contrastOnBackground = (hex, opacity = 1) => {
  const channels = (color) => [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16));
  const background = channels(COLORS.bg);
  const blended = channels(hex).map((c, i) => c * opacity + background[i] * (1 - opacity));
  const luminance = (rgb) => {
    const [r, g, b] = rgb.map(v => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const [hi, lo] = [luminance(blended), luminance(background)].sort((a, b) => b - a);
  return (hi + 0.05) / (lo + 0.05);
};

export const prefersReducedMotion = () => (
  window.matchMedia('(prefers-reduced-motion: reduce)').matches
);
