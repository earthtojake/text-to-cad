// /docs/search.json: what the documentation's search reads (components/docs/search.tsx), every page
// cut at its headings. Built once, with the site.
import { searchRecords } from "@/lib/docs/source";

export const dynamic = "force-static";

export function GET() {
  return Response.json(searchRecords());
}
