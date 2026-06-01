/** Brawlify CDN — images keyed by Supercell brawler id (e.g. 16000032). */
export function brawlerPortraitUrl(brawlerId: number): string {
  return `https://cdn.brawlify.com/brawlers/borderless/${brawlerId}.png`;
}

export function brawlerInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return "?";
  }
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}
