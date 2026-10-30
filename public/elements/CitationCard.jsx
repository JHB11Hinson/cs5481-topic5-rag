// Source panel for one citation, rendered in the Chainlit sidebar.
//
// Chainlit 2.3.0 fetches `/public/elements/CitationCard.jsx` when the element is
// sent and evaluates it in the browser with `props` in scope and a small `import`
// map (react, lucide-react, @/components/ui/*). The highlighted text arrives as
// `chunk_html`, already escaped server-side with the cited span wrapped in
// `<mark>`, so the highlight can only ever cover bytes that exist in the chunk.

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ExternalLink } from "lucide-react";

export default function CitationCard() {
  const citation = props || {};
  const marker = String(citation.marker || "").replace(/[[\]]/g, "");
  const heading = citation.heading_path || "";
  const url = citation.url || "";

  return (
    <Card className="w-full">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          {marker ? <Badge variant="secondary">[{marker}]</Badge> : null}
          <span>{citation.doc_title || citation.doc_id}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {heading ? (
          <div className="text-muted-foreground">{heading}</div>
        ) : null}
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 underline break-all"
          >
            <ExternalLink className="h-3 w-3 shrink-0" />
            {url}
          </a>
        ) : null}
        {citation.claim ? (
          <div className="font-medium">{citation.claim}</div>
        ) : null}
        <div
          className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap rounded-md bg-muted p-3 font-mono text-xs leading-relaxed"
          dangerouslySetInnerHTML={{ __html: citation.chunk_html || "" }}
        />
        <div className="text-xs text-muted-foreground">
          chunk {citation.chunk_id} · document {citation.doc_id}
        </div>
      </CardContent>
    </Card>
  );
}
