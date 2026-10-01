import type { Metadata } from "next";
import { IssuesLink, LegalPage, LegalSection } from "@/components/legal-page";

const summary =
  "text-to-cad is free, open-source software. It runs locally on your computer and does not track you.";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: summary,
  alternates: { canonical: "/privacy-policy" },
};

export default function PrivacyPolicyPage() {
  return (
    <LegalPage title="Privacy Policy" updated="October 1, 2026" summary={summary}>
      <LegalSection title="What we collect">
        Nothing. text-to-cad has no accounts, no telemetry and no analytics. It does not collect,
        store or send your personal data, your usage, or your models and files to us.
      </LegalSection>
      <LegalSection title="Your files">
        Your models, drawings and builds stay on your computer, where your agent and the local
        text-to-cad runtime work on them.
      </LegalSection>
      <LegalSection title="Network requests">
        The app you install text-to-cad into downloads its pinned runtime, the open-source cadgen
        package, from PyPI the first time it starts after an install or an update. The CAD viewer
        asks GitHub for the latest release at most every few hours, to offer updates; that request
        carries nothing about you or your work. When you ask your agent to, skills contact the
        services a task needs, such as step.parts to find parts or your own printer on your network;
        those requests go straight to those services, under their own privacy policies.
      </LegalSection>
      <LegalSection title="This website">
        texttocad.dev counts page views with Vercel Web Analytics, which sets no cookies and does
        not identify individual visitors.
      </LegalSection>
      <LegalSection title="Contact">
        Questions about privacy: open an issue at <IssuesLink />.
      </LegalSection>
    </LegalPage>
  );
}
