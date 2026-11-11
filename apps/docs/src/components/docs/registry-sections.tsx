import { Check, LinkIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { generatedKind, operationCommand, writers } from "@/lib/docs/generated";
import { documentType, integration, registry, usesOf, viewSummaries } from "@/lib/docs/registry";
import { withCode } from "@/lib/with-code";

/**
 * The sections a page gets from the library's registry, under its written text: the list of every
 * document type and integration, each one's facts, its operations and what writes it, and the
 * operations each type has. They say what `python -m cad.registry <name>` says, from the same table.
 */

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <>
      <h2 id={id} className="group/heading">
        {title}
        <a href={`#${id}`} className="docs-anchor" aria-label="Link to this section">
          <LinkIcon aria-hidden="true" />
        </a>
      </h2>
      {children}
    </>
  );
}

function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="docs-facts">
      {rows.map(([name, value]) => (
        <div key={name}>
          <dt>{name}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

const Codes = ({ values }: { values: string[] }) =>
  values.map((value, index) => (
    <span key={value}>
      {index ? " " : null}
      <code>{value}</code>
    </span>
  ));

const IntegrationLink = ({ name }: { name: string }) => (
  <Link href={`/docs/integrations/${name}`}>
    <code>{name}</code>
  </Link>
);

function DocumentTypes() {
  return (
    <Section id="all-document-types" title="All document types">
      <div className="docs-table">
        <table>
          <thead>
            <tr>
              <th>Type</th>
              <th>Id</th>
              <th>Files</th>
              <th>Viewed as</th>
              <th>Operations</th>
            </tr>
          </thead>
          <tbody>
            {registry.documentTypes.map((entry) => (
              <tr key={entry.id}>
                <td>
                  <Link href={`/docs/document-types/${entry.id}`}>{entry.title === "model" ? "Model" : entry.title}</Link>
                </td>
                <td>
                  <code>{entry.id}</code>
                </td>
                <td>{entry.extensions.length ? <Codes values={entry.extensions} /> : "none"}</td>
                <td>{entry.view}</td>
                <td>
                  <Codes values={entry.operations.map((operation) => operation.name)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function Integrations() {
  return (
    <Section id="all-integrations" title="All integrations">
      <div className="docs-table">
        <table>
          <thead>
            <tr>
              <th>Integration</th>
              <th>Extra</th>
              <th>What it brings</th>
              <th>Download</th>
            </tr>
          </thead>
          <tbody>
            {registry.integrations.map((entry) => (
              <tr key={entry.name}>
                <td>
                  <IntegrationLink name={entry.name} />
                </td>
                <td>{entry.extra ? <code>{`cad[${entry.extra}]`}</code> : "none"}</td>
                <td>{entry.holds}</td>
                <td className="whitespace-nowrap">about {entry.downloadMb} MB</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function DocumentType({ id }: { id: string }) {
  const entry = documentType(id)!;
  return (
    <>
      <Section id="facts" title="Facts">
        <Facts
          rows={[
            ["Id", <code key="id">{entry.id}</code>],
            ["What it is", entry.summary],
            ["Files", entry.extensions.length ? <Codes values={entry.extensions} /> : "None: a model is held by the engine and named by its document id"],
            ...(entry.mime ? ([["MIME type", <code key="mime">{entry.mime}</code>]] as [string, ReactNode][]) : []),
            ["Viewed as", `${entry.view}: ${viewSummaries[entry.view]}`],
            ["Carries", entry.content.join(", ")],
            ["In Python", <code key="python">{`cad.${entry.id}`}</code>],
          ]}
        />
      </Section>
      <Section id="operations" title="Operations">
        <div className="docs-table">
          <table>
            <thead>
              <tr>
                <th>Operation</th>
                <th>What it does</th>
                <th>Needs</th>
              </tr>
            </thead>
            <tbody>
              {entry.operations.map((operation) => (
                <tr key={operation.name}>
                  <td>
                    <code className="whitespace-nowrap">{operationCommand(entry.id, operation.name)}</code>
                  </td>
                  <td>{operation.summary}</td>
                  <td>{operation.integration ? <IntegrationLink name={operation.integration} /> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
      <Section id="what-writes-it" title="What writes it">
        <ul>
          {writers(entry.id).map((line) => (
            <li key={line}>{withCode(line)}</li>
          ))}
        </ul>
      </Section>
    </>
  );
}

function Integration({ name }: { name: string }) {
  const entry = integration(name)!;
  const uses = usesOf(name);
  const runs: Record<string, string> = {
    "in-process": "Inside the Python process that calls it",
    separate: "As a separate program",
    both: "Inside the calling process, and as a separate program",
  };
  return (
    <>
      <Section id="facts" title="Facts">
        <Facts
          rows={[
            ["Name", <code key="name">{entry.name}</code>],
            ["What it is", entry.summary],
            ["Extra", entry.extra ? <code key="extra">{`cad[${entry.extra}]`}</code> : "None"],
            ["Brings", `${entry.holds}, about ${entry.downloadMb} MB to download`],
            ["Runs", runs[entry.process] ?? entry.process],
            ...(entry.alongside.length
              ? ([["Installed with", entry.alongside.map((other, index) => (
                  <span key={other}>
                    {index ? ", " : null}
                    <IntegrationLink name={other} />
                  </span>
                ))]] as [string, ReactNode][])
              : []),
            ...(entry.platforms.length ? ([["Platforms", entry.platforms.join(", ")]] as [string, ReactNode][]) : []),
            ...(entry.python ? ([["Python", entry.python]] as [string, ReactNode][]) : []),
            ...(entry.commands.length
              ? ([["Commands", <Codes key="commands" values={entry.commands.map((command) => `cad run ${command}`)} />]] as [string, ReactNode][])
              : []),
            ...(entry.program
              ? ([["Program", <>
                  <code>{entry.program.name}</code> {entry.program.minimum} or newer; <code>{entry.program.override}</code> names another
                </>]] as [string, ReactNode][])
              : []),
            ["Python packages", <Codes key="packages" values={entry.distributions} />],
          ]}
        />
      </Section>
      {entry.operations.length ? (
        <Section id="operations" title="Operations">
          <div className="docs-table">
            <table>
              <thead>
                <tr>
                  <th>Operation</th>
                  <th>What it does</th>
                </tr>
              </thead>
              <tbody>
                {entry.operations.map((operation) => (
                  <tr key={operation.name}>
                    <td>
                      <code className="whitespace-nowrap">{`cad ${entry.name} ${operation.name} <file>`}</code>
                    </td>
                    <td>
                      {operation.summary} (<Codes values={entry.files} />)
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      ) : null}
      {uses.length ? (
        <Section id="where-it-is-used" title="Where it is used">
          <ul>
            {uses.map(({ type, uses: names }) => (
              <li key={type.id}>
                <Link href={`/docs/document-types/${type.id}`}>{type.title === "model" ? "Model" : type.title}</Link>: {names.join(", ")}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </>
  );
}

function Operations() {
  return (
    <div className="docs-table">
      <table>
        <thead>
          <tr>
            <th>Type</th>
            {registry.operations.map((name) => (
              <th key={name}>
                <code>{name}</code>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {registry.documentTypes.map((entry) => (
            <tr key={entry.id}>
              <td>
                <Link href={`/docs/document-types/${entry.id}`}>
                  <code>{entry.id}</code>
                </Link>
              </td>
              {registry.operations.map((name) => (
                <td key={name} className="text-center">
                  {entry.operations.some((operation) => operation.name === name) ? (
                    <Check className="mx-auto size-4 text-brand" aria-label="yes" />
                  ) : null}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RegistrySections({ slug }: { slug: string }) {
  const generated = generatedKind(slug);
  if (!generated) return null;
  return (
    <div className="docs-prose">
      {generated.kind === "document-types" ? <DocumentTypes /> : null}
      {generated.kind === "integrations" ? <Integrations /> : null}
      {generated.kind === "document-type" ? <DocumentType id={generated.id} /> : null}
      {generated.kind === "integration" ? <Integration name={generated.name} /> : null}
      {generated.kind === "operations" ? <Operations /> : null}
    </div>
  );
}
