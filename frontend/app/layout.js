import "./globals.css";

export const metadata = {
  title: "TranscriptIQ — AI Video Transcripts & Summaries",
  description:
    "Extract transcripts from YouTube or any video platform and get polished, AI-crafted summaries powered by Google Gemini.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
