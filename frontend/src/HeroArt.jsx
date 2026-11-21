// Decorative illustration for the public screens (a book connected to GitHub and living docs).
// Purely visual: the motion is CSS (see theme.css) and stops for users who prefer reduced motion.
export default function HeroArt() {
  return (
    <svg viewBox="0 0 560 230" role="img" aria-label="A book connected to GitHub and living docs">
      <defs>
        <linearGradient id="hero-book" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#cfe0ff" stopOpacity=".9" />
          <stop offset="1" stopColor="#6f86ff" stopOpacity=".35" />
        </linearGradient>
        <linearGradient id="hero-page" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#8da0ff" stopOpacity=".55" />
          <stop offset="1" stopColor="#3a4ad0" stopOpacity=".15" />
        </linearGradient>
      </defs>
      <ellipse className="orb" cx="280" cy="118" rx="215" ry="62" fill="none" stroke="#3a4a78" strokeWidth="1" opacity=".8" />
      <ellipse className="orb orb-reverse" cx="280" cy="118" rx="150" ry="86" fill="none" stroke="#2c3a62" strokeWidth="1" opacity=".8" />
      <g fill="#8da0ff">
        <circle className="twinkle" cx="110" cy="40" r="1.6" />
        <circle className="twinkle t1" cx="470" cy="60" r="1.4" />
        <circle className="twinkle t2" cx="330" cy="30" r="1.2" />
        <circle className="twinkle t3" cx="60" cy="150" r="1.3" />
        <circle className="twinkle t1" cx="520" cy="120" r="1.5" />
        <circle className="twinkle t2" cx="200" cy="200" r="1.2" />
      </g>
      <g transform="translate(250 38)">
        <g className="float">
          <path d="M0 14 L58 0 L58 128 L0 142 Z" fill="url(#hero-book)" stroke="#bcd0ff" strokeOpacity=".6" />
          <path d="M58 0 L96 12 L96 140 L58 128 Z" fill="url(#hero-page)" stroke="#8da0ff" strokeOpacity=".5" />
          <path d="M10 40 L48 31 M10 58 L48 49 M10 76 L48 67" stroke="#fff" strokeOpacity=".5" strokeWidth="2" strokeLinecap="round" />
        </g>
      </g>
      <g transform="translate(372 78)">
        <g className="float f2">
          <rect width="84" height="50" rx="7" fill="url(#hero-page)" stroke="#8da0ff" strokeOpacity=".5" transform="skewX(-14)" />
          <rect y="18" width="84" height="50" rx="7" fill="url(#hero-page)" stroke="#8da0ff" strokeOpacity=".4" transform="skewX(-14)" />
        </g>
      </g>
      <g transform="translate(96 86)">
        <g className="float f3">
          <rect width="74" height="48" rx="7" fill="#101a30" stroke="#5d74d8" strokeOpacity=".6" transform="skewX(-14)" />
          <path d="M14 15h34M14 25h44M14 35h26" stroke="#62d6ea" strokeOpacity=".7" strokeWidth="2" strokeLinecap="round" transform="skewX(-14)" />
        </g>
      </g>
      <g fontFamily="JetBrains Mono, Cascadia Mono, Consolas, monospace" fontSize="10">
        <g className="float f3">
          <rect x="26" y="44" width="62" height="22" rx="6" fill="#0e1626" stroke="#2a3a60" />
          <text x="58" y="59" fill="#aebbe0" textAnchor="middle">GitHub</text>
        </g>
        <g className="float f2">
          <rect x="446" y="158" width="84" height="22" rx="6" fill="#0e1626" stroke="#2a3a60" />
          <text x="488" y="173" fill="#aebbe0" textAnchor="middle">Living docs</text>
        </g>
        <text x="280" y="214" fill="#5d6a87" textAnchor="middle" letterSpacing="2">CONNECTED BY INTELLIGENCE</text>
      </g>
    </svg>
  );
}
