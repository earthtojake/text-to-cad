import type { Metadata } from "next";
import { IssuesLink, LegalPage, LegalSection } from "@/components/legal-page";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "How Thompson Labs LLC handles personal data for text-to-cad: what is collected, why, who receives it, how long it is kept, and your controls.",
  alternates: { canonical: "/privacy-policy" },
};

export default function PrivacyPolicyPage() {
  return (
    <LegalPage title="Privacy Policy" updated="October 1, 2026">
      <LegalSection>
        <p>
          This policy describes how Thompson Labs LLC (“we”, “us”) handles personal data for
          text-to-cad: the text-to-cad plugin and its skills, the cadgen software they run, the
          step.parts part library they search, and this website, texttocad.dev. text-to-cad runs on
          your computer. Your prompts, models, drawings and files stay there, and we do not collect
          them.
        </p>
      </LegalSection>

      <LegalSection title="1. Personal data we collect">
        <ul>
          <li>
            <strong>The plugin and cadgen:</strong> none. There are no accounts, telemetry, analytics
            or crash reports. Your agent and the local runtime process your work on your computer and
            do not send it to us.
          </li>
          <li>
            <strong>step.parts searches:</strong> when you ask your agent to find a part, the
            step-parts skill sends your search terms and the parts you request to step.parts. Each
            request includes standard metadata: your IP address, the time and the user agent.
          </li>
          <li>
            <strong>This website:</strong> page views, with the referring page, browser, device type
            and country, through Vercel Web Analytics, which sets no cookies. Each request also
            includes standard metadata: your IP address, the time and the user agent.
          </li>
        </ul>
        <p>
          We do not collect payment card data, health information, government identifiers, passwords,
          API keys or other credentials, or any sensitive category of personal data.
        </p>
      </LegalSection>

      <LegalSection title="2. How we use it">
        <ul>
          <li>Search terms and part requests: only to return the parts and files you asked for.</li>
          <li>Request metadata: only to deliver, secure and troubleshoot step.parts and this website.</li>
          <li>Page-view statistics: only to understand, in aggregate, how this website is used.</li>
        </ul>
        <p>
          We do not sell personal data, use it for advertising, or build profiles of you, and we do
          not track you across other sites or services.
        </p>
      </LegalSection>

      <LegalSection title="3. Who receives it">
        <ul>
          <li>
            <strong>Vercel Inc.</strong>, which hosts step.parts and this website and processes their
            requests for us.
          </li>
          <li>
            <strong>Services the software contacts directly</strong>, under their own privacy
            policies. The agent app installs the pinned cadgen runtime from the Python Package Index
            (PyPI) the first time it starts after an install or an update. The CAD viewer asks GitHub
            for the latest release at most every six hours, to offer updates. Skills reach the
            services you ask your agent to use, such as a fabrication service’s public specifications
            or your own printer on your local network. These requests send no personal data of ours;
            each service sees the request’s IP address, time and user agent.
          </li>
        </ul>
        <p>We share personal data with no one else, except where the law requires it.</p>
      </LegalSection>

      <LegalSection title="4. How long we keep it">
        <ul>
          <li>
            step.parts searches and request metadata are kept only in our hosting provider’s request
            logs, which are deleted within 30 days.
          </li>
          <li>
            Website analytics are kept as aggregate page-view statistics. The visitor identifier
            Vercel derives from a request is discarded after 24 hours.
          </li>
          <li>Everything text-to-cad stores locally stays on your computer until you delete it.</li>
        </ul>
      </LegalSection>

      <LegalSection title="5. Your choices and controls">
        <ul>
          <li>
            The plugin works without contacting us. step.parts receives a request only when you ask
            your agent to search for or download a part.
          </li>
          <li>
            You can uninstall the plugin at any time. Deleting cadgen’s cache and state folders
            removes everything it stored on your computer, including its recent-files list.
          </li>
          <li>You can block this website’s analytics with your browser’s settings or a content blocker.</li>
          <li>
            You can ask us what personal data we hold about you, or ask us to delete it, using the
            contact below.
          </li>
        </ul>
      </LegalSection>

      <LegalSection title="6. Children">
        <p>
          text-to-cad is not directed to children under 13, and we do not knowingly collect their
          personal data.
        </p>
      </LegalSection>

      <LegalSection title="7. Changes">
        <p>We will post any change to this policy on this page and update the date above.</p>
      </LegalSection>

      <LegalSection title="8. Contact">
        <p>
          Thompson Labs LLC. For privacy questions and requests, open an issue at <IssuesLink />.
        </p>
      </LegalSection>
    </LegalPage>
  );
}
