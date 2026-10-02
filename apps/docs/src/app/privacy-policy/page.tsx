import type { Metadata } from "next";
import { IssuesLink, LegalPage, LegalSection } from "@/components/legal-page";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "How Thompson Labs LLC handles personal data for text-to-cad: what is collected, including the CAD app's anonymous usage analytics, why, who receives it, how long it is kept, and your controls.",
  alternates: { canonical: "/privacy-policy" },
};

export default function PrivacyPolicyPage() {
  return (
    <LegalPage title="Privacy Policy" updated="October 2, 2026">
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
            <strong>The plugin and cadgen:</strong> your prompts, models, drawings, file names and
            paths never leave your computer. There are no accounts and no crash reports. Your agent and
            the local runtime process your work on your computer and do not send it to us.
          </li>
          <li>
            <strong>Usage analytics from the CAD app, when they are on:</strong> the CAD app that
            shows models in your agent app (the plugin’s <code>cad</code> server) sends
            api.texttocad.dev, at most once a minute while you use it: a random install ID created on
            your computer; a random ID for each time the app starts it; the cadgen version, whether it
            was installed from a plugin directory or by hand, your operating system and processor
            type, and the name and version of your agent app and how it shows CAD; how many times each
            CAD tool was called and failed, and how many times you touched a CAD view; and, once a day
            for each distinct file CAD shows, a one-way code made from where the file is with a secret
            key that never leaves your computer, and the file’s format (such as STEP or STL). The code
            lets us count how many different files are used without learning their names, locations or
            contents, and it means nothing on any other computer. We record the time each batch
            arrives. Nothing is sent while CAD sits unused. Analytics never include your files, models,
            file or folder names, prompts, tool arguments or anything you type. Like any request over
            the internet, each one also reaches our host with your IP address, the time and a user
            agent (for the CAD app, just “cadgen”); see section 4 for what happens to them. Section 5 says when they are on
            and how to turn them off. The skills alone, without the CAD app, send no analytics.
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
          <li>
            Request metadata: only to deliver, secure and troubleshoot step.parts, api.texttocad.dev
            and this website.
          </li>
          <li>Page-view statistics: only to understand, in aggregate, how this website is used.</li>
          <li>
            Usage analytics: only to understand, in aggregate, how many people use text-to-cad and how
            often, how many files they work on and in which formats, which CAD features are used, which
            agent apps and operating systems to support, and how often tools fail.
          </li>
        </ul>
        <p>
          We do not sell personal data, use it for advertising, or build profiles of you, and we do
          not track you across other sites or services.
        </p>
      </LegalSection>

      <LegalSection title="3. Who receives it">
        <ul>
          <li>
            <strong>Vercel Inc.</strong>, which hosts step.parts, this website and api.texttocad.dev
            and processes their requests for us, and <strong>Neon</strong>, which hosts the database
            that stores usage analytics for us. Neon never sees your IP address: only our servers
            connect to it.
          </li>
          <li>
            <strong>Services the software contacts directly</strong>, under their own privacy
            policies. The agent app installs the pinned cadgen runtime from the Python Package Index
            (PyPI) the first time it starts after an install or an update. The browser CAD viewer
            (<code>cadgen viewer</code>) asks GitHub for the latest release at most every few hours, to
            offer updates; the CAD app in your agent app does not. Skills reach the
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
            Vercel, our host, records each request to step.parts, api.texttocad.dev and this website
            in its request logs, with the IP address, time and user agent it arrived with. We use those
            logs only to run and secure the services, and they are deleted within 30 days. step.parts
            searches are kept only there.
          </li>
          <li>
            Website analytics are kept as aggregate page-view statistics. The visitor identifier
            Vercel derives from a request is discarded after 24 hours.
          </li>
          <li>
            Usage analytics are kept for 13 months, then deleted. We do not store IP addresses with
            them, and no request log pairs an IP address with an install ID: the ID travels inside the
            request, which those logs do not record. Turning analytics off deletes everything stored under your install ID; if our server
            cannot be reached at that moment, the CAD app asks again until it can.
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
            <strong>Usage analytics are off until you allow them</strong>, however you installed
            text-to-cad. The CAD app asks you once, and sends nothing unless you choose Allow. Your
            answer is kept on your computer through restarts and updates. If we ever collect more than
            this policy describes, the CAD app asks you again first. An agent app that does not show
            the CAD app never asks, and sends nothing.
          </li>
          <li>
            To change your answer later, use <strong>Share anonymous usage data</strong> in the CAD app’s
            Settings (on its home page, or with a 3D model open). To turn analytics off, you can also ask your agent to turn off CAD analytics, or run{" "}
            <code>uvx cadgen analytics off</code>. Turning them off deletes the install ID on your
            computer, with the secret key behind the file codes, and asks our server to delete everything
            stored under it. Turning them on again starts a new install ID and key, so nothing links the two. Setting{" "}
            <code>DO_NOT_TRACK=1</code> or <code>CADGEN_ANALYTICS=0</code> in your agent app’s
            environment keeps them off there whatever else is chosen. <code>uvx cadgen analytics
            on</code> turns them on, and <code>uvx cadgen analytics status</code> shows the setting and
            your install ID.
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
