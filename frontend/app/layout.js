import "./globals.css";

export const metadata = {
  title: "Transcript Extractor",
  description:
    "Extract transcripts from YouTube or any video platform and get refined summaries.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
