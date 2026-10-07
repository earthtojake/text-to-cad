import type { Metadata } from "next";
import { IssuesLink, LegalPage, LegalSection } from "@/components/legal-page";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "How Thompson Labs LLC handles personal data for text-to-cad: what is collected, including cadgen's telemetry (usage counts and crash reports) and its daily version check, why, who receives it, how long it is kept, and your controls.",
  alternates: { canonical: "/privacy-policy" },
};

export default function PrivacyPolicyPage() {
  return (
    <LegalPage title="Privacy Policy" updated="October 7, 2026">
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
            paths never leave your computer. There are no accounts. Your agent and the local runtime
            process your work on your computer and do not send it to us.
          </li>
          <li>
            <strong>Telemetry: usage counts and crash reports, when it is on.</strong> cadgen’s
            long-running parts -- the CAD app that shows models in your agent app (the plugin’s{" "}
            <code>cad</code> server), the CAD viewer in your browser (<code>cadgen viewer</code>) and
            the build daemon that builds models for them and for every <code>cadgen</code> command --
            send to api.texttocad.dev, at most once every five minutes while you use them and once as
            each stops:
            <ul>
              <li>
                a random install ID created on your computer, and a random ID for each time one of
                them starts;
              </li>
              <li>
                which of them sent it, the cadgen version, where it was installed from (a plugin
                directory, the Cursor Marketplace, GitHub, or a development install), your operating
                system and processor type, and the name and version of your agent app and how it shows
                CAD (or that it is the browser viewer);
              </li>
              <li>
                counts, added up over those five minutes: how many times each CAD tool was called and
                failed; how many times you touched a CAD view; how many different files of each format
                (such as STEP or STL) a CAD view showed for the first time that day, told apart on your
                computer and sent only as a number; how many models were built, of which format,
                whether a model script or a <code>cadgen</code> command asked, how they ended
                (finished, failed, crashed or stopped), how many came from cadgen’s cache, and how long
                they took; how many snapshots were rendered, of which format, how many failed and how
                long they took; how many times assemblies, mesh exports, posed joints, animations,
                engineering drawings and Quick Edit were used; and how many of the build daemon’s
                workers started, crashed or were replaced, and how many builds it turned away for want
                of memory;
              </li>
              <li>
                crash reports, when cadgen’s own code fails unexpectedly: the error’s type (such as
                “KeyError”), whether the program carried on, and where in code it failed -- file paths
                inside cadgen, Python’s standard library, cadgen’s own open-source dependencies or the
                CAD app’s and viewer’s page scripts, with function names and line numbers -- or, for a
                build worker that stopped, its exit status. Any part of the failure in your own code is
                replaced by a placeholder, and a crash report never includes the error’s message, any
                values, your files, or file or folder names.
              </li>
            </ul>
            We record the time each batch arrives, and our server adds the country each request comes
            from, which it works out from your IP address; it keeps neither the address nor anything
            finer than the country. Nothing is sent while cadgen sits unused. Telemetry never includes
            your files, models, file or folder names, prompts, tool arguments or anything you type. A{" "}
            <code>cadgen</code> command sends nothing itself: it hands what it counted (a snapshot, a
            drawing, a crash) to the build daemon if one is running, which sends it with its own. Like any
            request over the internet, each one also reaches our host with your IP address, the time
            and a user agent (for cadgen, just “cadgen”); see section 4 for what happens to them.
            Section 5 says when telemetry is on and how to turn it off.
          </li>
          <li>
            <strong>The version check:</strong> at most once a day, cadgen (the CAD app or the CAD viewer)
            asks api.texttocad.dev which text-to-cad release is the
            newest, so it can tell you when there is an update. The request carries no ID and nothing
            about you or your work; like any request, it reaches our host with your IP address, the
            time and a user agent (“cadgen”). It is never made in CI or for a copy that a plugin directory,
            the Cursor Marketplace or Gemini updates, and section 5 says how to turn it off.
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
          <li>Version checks: only to answer them; we keep nothing from them beyond our host’s request logs.</li>
          <li>
            Telemetry: only to understand, in aggregate, how many people use text-to-cad and how
            often, how many files they work on and in which formats, what they build and how long it
            takes, where in the world it is used, which features are used, which agent apps and
            operating systems to support, and how often tools, builds and snapshots fail; and, from
            crash reports, to find and fix the bugs behind them.
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
            and processes their requests for us, and <strong>PostHog, Inc.</strong>, which stores and
            analyzes telemetry for us. PostHog never sees your IP address: only our server sends it
            telemetry, with the country it worked out and PostHog’s own location lookup turned off.
          </li>
          <li>
            <strong>Services the software contacts directly</strong>, under their own privacy
            policies. The agent app installs the pinned cadgen runtime from the Python Package Index
            (PyPI) the first time it starts after an install or an update. Skills reach the
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
            Telemetry is kept by PostHog for as long as our plan with it keeps events, currently one
            year, then deleted. We do not store IP addresses with it. Your install ID travels in the
            body of each request, which our host’s request logs do not record, and we never combine
            telemetry with those logs. Turning telemetry off deletes everything stored under your
            install ID; PostHog carries the deletion out in the background, which can take some days.
            If our server cannot be reached at that moment, cadgen asks again until it can.
          </li>
          <li>Everything text-to-cad stores locally stays on your computer until you delete it.</li>
        </ul>
      </LegalSection>

      <LegalSection title="5. Your choices and controls">
        <ul>
          <li>
            The plugin works without contacting us, apart from the daily version check. step.parts
            receives a request only when you ask your agent to search for or download a part.
          </li>
          <li>
            <strong>Telemetry is on once cadgen has told you.</strong> The first <code>cadgen</code>{" "}
            command you or your agent run says, once, in its output, that cadgen sends usage stats and
            crash reports and how to turn them off, and nothing is sent before that. If we ever send more than this
            policy describes, cadgen says so again before it does. Nothing is sent by default in CI or
            from a development install. Your choice is kept on your computer, as the{" "}
            <code>telemetry</code> setting in cadgen’s settings file, through restarts and updates, and
            one choice counts for every part of cadgen; a no stays a no. If you turned analytics off in
            an earlier version of text-to-cad, telemetry stays off. Turning telemetry off also turns off
            analytics in an earlier version still installed, and deletes what it sent.
          </li>
          <li>
            To turn telemetry off, run <code>uvx cadgen telemetry off</code>, use{" "}
            <strong>Share usage stats</strong> in the menu of the CAD app or the CAD viewer (the logo
            at the top left, over any open model), or ask your agent to turn off CAD telemetry.
            Turning it off deletes the install ID on your computer and asks our server to delete
            everything stored under it. Turning it on again starts a new install ID, so nothing links
            the two. Setting <code>DO_NOT_TRACK=1</code> or <code>CADGEN_TELEMETRY=0</code> where cadgen
            runs (your agent app’s environment, or the shell that runs a <code>cadgen</code> command)
            keeps it off there whatever else is chosen. <code>uvx cadgen telemetry on</code> turns it
            on, and <code>uvx cadgen telemetry status</code> shows the setting and your install ID.
          </li>
          <li>
            Setting <code>CADGEN_UPDATE_CHECK=0</code> where cadgen runs turns the daily version check
            off; CAD then never says when there is an update.
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
