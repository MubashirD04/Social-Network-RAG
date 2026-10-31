// The landing page's single color story: scrolling walks this ramp, and both
// the CSS accents (--flow) and the 3D nodes read from it, so they move together.
export const FLOW_COLORS = ['#4ECDC4', '#60A5FA', '#A78BFA', '#F472B6', '#F4A261'];
export const FLOW_STOPS = FLOW_COLORS.map((_, i) => i / (FLOW_COLORS.length - 1));
