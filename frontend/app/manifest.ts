import type { MetadataRoute } from "next";

// Lets the /ride recorder be "installed" on a phone home screen for the live demo.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "CityEcho",
    short_name: "CityEcho",
    description: "Warsaw's buses verify its citizens — and its citizens verify its buses",
    start_url: "/ride",
    display: "standalone",
    background_color: "#f3f3f0",
    theme_color: "#4a3aa7",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
  };
}
