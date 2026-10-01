import type { Metadata } from "next";
import Link from "next/link";
import { IssuesLink, LegalPage, LegalSection } from "@/components/legal-page";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "The terms for using text-to-cad, provided by Thompson Labs LLC.",
  alternates: { canonical: "/terms-of-service" },
};

export default function TermsOfServicePage() {
  return (
    <LegalPage title="Terms of Service" updated="October 1, 2026">
      <LegalSection>
        <p>
          These terms govern your use of text-to-cad, provided by Thompson Labs LLC (“we”, “us”): the
          text-to-cad plugin and its skills, the cadgen software they run, the step.parts part
          library, and this website, texttocad.dev. By using text-to-cad you agree to them.
        </p>
      </LegalSection>

      <LegalSection title="1. License">
        <p>
          text-to-cad’s software is released under the{" "}
          <a
            className="underline underline-offset-4 hover:text-foreground"
            href="https://github.com/earthtojake/text-to-cad/blob/main/LICENSE"
          >
            MIT License
          </a>
          , which governs how you may use, copy, modify and distribute it.
        </p>
      </LegalSection>

      <LegalSection title="2. Your content">
        <p>
          Your prompts, models and files stay yours. text-to-cad processes them on your computer, and
          we claim no rights in them or in what you make with it.
        </p>
      </LegalSection>

      <LegalSection title="3. Acceptable use">
        <p>
          Do not use step.parts or this website to break the law, infringe anyone’s rights, or
          disrupt or overload the services.
        </p>
      </LegalSection>

      <LegalSection title="4. Outside services">
        <p>
          Services you reach through text-to-cad, such as package indexes, GitHub, fabrication
          services and printers, are governed by their own terms.
        </p>
      </LegalSection>

      <LegalSection title="5. No warranty">
        <p>
          text-to-cad and step.parts are provided “as is”, without warranty of any kind. Check
          generated models, drawings and manufacturing files before you fabricate, order or rely on
          them.
        </p>
      </LegalSection>

      <LegalSection title="6. Limitation of liability">
        <p>
          To the fullest extent the law allows, Thompson Labs LLC is not liable for any indirect,
          incidental, special or consequential damages, or for any loss arising from your use of
          text-to-cad.
        </p>
      </LegalSection>

      <LegalSection title="7. Privacy">
        <p>
          The{" "}
          <Link className="underline underline-offset-4 hover:text-foreground" href="/privacy-policy">
            Privacy Policy
          </Link>{" "}
          describes how we handle personal data.
        </p>
      </LegalSection>

      <LegalSection title="8. Changes">
        <p>
          We will post any change to these terms on this page and update the date above. Using
          text-to-cad after a change means you accept it.
        </p>
      </LegalSection>

      <LegalSection title="9. Contact">
        <p>
          Thompson Labs LLC. For questions about these terms, open an issue at <IssuesLink />.
        </p>
      </LegalSection>
    </LegalPage>
  );
}
