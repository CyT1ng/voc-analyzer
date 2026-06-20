// A subtle, decorative wall of real-feeling customer voices drifting horizontally behind the
// landing screen — many platforms, many product types.

interface Voice {
  platform: string;
  product: string;
  text: string;
}

const VOICES: Voice[] = [
  { platform: "reddit", product: "headphones", text: "ANC is genuinely better than my Bose, no regrets" },
  { platform: "youtube", product: "earbuds", text: "battery died after two hours, returning these" },
  { platform: "x", product: "running shoes", text: "300 miles in and they still feel brand new" },
  { platform: "tiktok", product: "skincare", text: "broke me out in a week, wish I'd read reviews first" },
  { platform: "youtube", product: "phone", text: "camera is unreal but it gets so hot while gaming" },
  { platform: "reddit", product: "keyboard", text: "stabilizers rattle out of the box, had to lube them" },
  { platform: "instagram", product: "espresso machine", text: "café-quality shots at home, worth every penny" },
  { platform: "x", product: "laptop", text: "fans spin up at the slightest thing, kinda loud" },
  { platform: "reddit", product: "vacuum", text: "picks up dog hair like nothing else, obsessed" },
  { platform: "youtube", product: "smartwatch", text: "step count is wildly inaccurate on runs" },
  { platform: "tiktok", product: "blender", text: "smoothies in 20 seconds, this thing is a beast" },
  { platform: "instagram", product: "mattress", text: "back pain gone after two weeks, sleeping great" },
  { platform: "reddit", product: "monitor", text: "lovely panel but the stand wobbles a lot" },
  { platform: "x", product: "e-reader", text: "battery lasts weeks, perfect for travel" },
  { platform: "youtube", product: "drone", text: "wind resistance is impressive, buttery 4K footage" },
  { platform: "tiktok", product: "air fryer", text: "everything comes out crispy, never using the oven again" },
  { platform: "reddit", product: "graphics card", text: "runs cool and quiet, undervolts like a dream" },
  { platform: "instagram", product: "sneakers", text: "sizing runs small, order half a size up" },
  { platform: "x", product: "soundbar", text: "dialogue is so much clearer now, huge upgrade" },
  { platform: "youtube", product: "toothbrush", text: "gums stopped bleeding after a month" },
  { platform: "reddit", product: "backpack", text: "zippers broke within a month, disappointed" },
  { platform: "tiktok", product: "hair dryer", text: "cuts my drying time in half, worth the hype" },
  { platform: "instagram", product: "camera", text: "autofocus nails it every single time" },
  { platform: "x", product: "standing desk", text: "wobbles at full height, otherwise solid" },
];

function rotate<T>(arr: T[], n: number): T[] {
  const k = n % arr.length;
  return [...arr.slice(k), ...arr.slice(0, k)];
}

const ROWS = [
  { dur: 72, reverse: false },
  { dur: 96, reverse: true },
  { dur: 60, reverse: false },
  { dur: 110, reverse: true },
  { dur: 84, reverse: false },
  { dur: 100, reverse: true },
];

export default function VoiceBackground() {
  return (
    <div
      aria-hidden
      className="voice-mask pointer-events-none fixed inset-0 -z-10 flex flex-col justify-between gap-4 overflow-hidden py-10 opacity-70"
    >
      {ROWS.map((r, i) => {
        const items = [...rotate(VOICES, i * 5), ...rotate(VOICES, i * 5)];
        return (
          <div
            key={i}
            className="voice-row flex w-max gap-4"
            style={{
              animation: `${r.reverse ? "voice-marquee-reverse" : "voice-marquee"} ${r.dur}s linear infinite`,
            }}
          >
            {items.map((v, j) => (
              <VoiceCard key={j} {...v} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

function VoiceCard({ platform, product, text }: Voice) {
  return (
    <span className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-zinc-200/60 bg-white/60 px-3 py-2 text-xs dark:border-zinc-800/60 dark:bg-zinc-900/40">
      <span className="font-semibold uppercase tracking-wide text-zinc-400 dark:text-zinc-500">
        {platform}
      </span>
      <span className="text-zinc-500 dark:text-zinc-400">“{text}”</span>
      <span className="text-zinc-300 dark:text-zinc-600">{product}</span>
    </span>
  );
}
