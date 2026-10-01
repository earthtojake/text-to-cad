import type { Metadata } from "next";
import Link from "next/link";
import { IssuesLink, LegalPage, LegalSection } from "@/components/legal-page";

const summary =
  "text-to-cad is free, open-source software, released under the MIT License. It runs locally on your computer and does not track you.";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: summary,
  alternates: { canonical: "/terms-of-service" },
};

export default function TermsOfServicePage() {
  return (
    <LegalPage title="Terms of Service" updated="October 1, 2026" summary={summary}>
      <LegalSection title="Using text-to-cad">
        You may use, copy, modify and distribute text-to-cad under its{" "}
        <a
          className="underline underline-offset-4 hover:text-foreground"
          href="https://github.com/earthtojake/text-to-cad/blob/main/LICENSE"
        >
          MIT License
        </a>
        . There is no account, subscription or fee.
      </LegalSection>
      <LegalSection title="No warranty">
        text-to-cad is provided as is, without warranty of any kind, and its authors are not liable
        for any claim, damages or other liability arising from its use, as the MIT License sets out.
        Check generated models, drawings and manufacturing files before you fabricate, order or rely
        on them.
      </LegalSection>
      <LegalSection title="Outside services">
        Services you reach through text-to-cad, such as package indexes, part libraries, fabrication
        services and printers, have their own terms.
      </LegalSection>
      <LegalSection title="Privacy">
        text-to-cad collects nothing about you; see the{" "}
        <Link className="underline underline-offset-4 hover:text-foreground" href="/privacy-policy">
          Privacy Policy
        </Link>
        .
      </LegalSection>
      <LegalSection title="Contact">
        Questions about these terms: open an issue at <IssuesLink />.
      </LegalSection>
    </LegalPage>
  );
}
