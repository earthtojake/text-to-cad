import { filterModels, sortDocuments, type LibraryModel, type LibraryProject } from "../library/ModelLibrary.js";
import { lastActivity } from "../lib/age.js";

/** How many rows the search draws at most; past it, a line says how many more there are. */
export const SEARCH_LIMIT = 50;

/** The project a row's document is in, as the search names it; null, a standalone document. */
export interface SearchProject { id: string; name: string }
/** One document the search lists: the library's row of it, its key (one row a document) and its project. */
export interface SearchRow<Model extends LibraryModel = LibraryModel> {
  key: string;
  model: Model;
  project: SearchProject | null;
}
/**
 * A group of rows, in the order drawn: `here`, the project of the document on screen ("In <project>"); `other`, every
 * other document, under "Other projects"; `recent`, the latest documents where nothing is typed and the document on
 * screen is in no project; `found`, what a search finds where it is in none (one list, no heading).
 */
export interface SearchGroup<Model extends LibraryModel = LibraryModel> {
  id: "here" | "other" | "recent" | "found";
  rows: SearchRow<Model>[];
}

const slashed = (path: string) => String(path || "").replace(/\\/g, "/").replace(/\/+$/, "");
/** A document's key: its id where the host names one, else its path; a file both lists carry is one row by either. */
export const rowKey = (model: LibraryModel) => model.id || slashed(model.path);

/**
 * Every document the library lists, one row each: each project's documents (its project known from where it is
 * listed), then the documents opened before that no project lists (a standalone document, or one whose project is
 * named by its row alone). A document both lists carry is one row, the opened list's record of it (its times and pin
 * are that list's), its project the project's.
 */
export function searchRows<Model extends LibraryModel>(list: readonly Model[], projects: readonly LibraryProject<Model>[]): SearchRow<Model>[] {
  const named = new Map(projects.map(project => [project.id, { id: project.id, name: project.name }]));
  const rows = new Map<string, SearchRow<Model>>();
  const byPath = new Map<string, string>();
  const add = (model: Model, project: SearchProject | null) => {
    const key = rowKey(model), path = slashed(model.path);
    const known = rows.get(key) ?? rows.get(byPath.get(path) ?? "");
    if (known) {
      known.model = model;
      known.project = known.project ?? project;
      return;
    }
    rows.set(key, { key, model, project });
    byPath.set(path, key);
  };
  for (const project of projects) for (const model of project.documents) add(model, named.get(project.id)!);
  for (const model of list) add(model, model.project ? named.get(model.project) ?? null : null);
  return [...rows.values()];
}

const latestFirst = <Model extends LibraryModel>(rows: readonly SearchRow<Model>[]) => rows.map((row, index) => ({ row, index }))
  .sort((a, b) => (lastActivity(b.row.model) ?? 0) - (lastActivity(a.row.model) ?? 0) || a.index - b.index).map(({ row }) => row);
const inProjectOrder = <Model extends LibraryModel>(rows: readonly SearchRow<Model>[]) => {
  const order = sortDocuments(rows.map(row => row.model), "kind");
  const of = new Map(rows.map(row => [row.model, row]));
  return order.map(model => of.get(model)!);
};

/**
 * What the search shows for `query`, grouped, at most `limit` rows in all (`total`: how many there are).
 *
 * - Nothing typed: the documents of the project the document on screen is in (`project`), in the home's Sort by Kind
 *   (its 3D models, then its drawings, boards, schematics and robots, each by format and name); with no project, the
 *   latest documents.
 * - Typed: every document whose name has every word, or a file's path (the home's search, `filterModels`): those in
 *   that project first, in its order, then the rest, the latest first.
 */
export function searchGroups<Model extends LibraryModel>(rows: readonly SearchRow<Model>[], { query, project = null, limit = SEARCH_LIMIT }:
  { query: string; project?: string | null; limit?: number }): { groups: SearchGroup<Model>[]; total: number } {
  const typed = query.trim().length > 0;
  const found = typed ? new Set(filterModels(rows.map(row => row.model), query)) : null;
  const matching = found ? rows.filter(row => found.has(row.model)) : rows;
  const here = project ? matching.filter(row => row.project?.id === project || (!row.project && row.model.project === project)) : [];
  let groups: SearchGroup<Model>[];
  if (project && !typed) groups = [{ id: "here", rows: inProjectOrder(here) }];
  else if (!project) groups = [{ id: typed ? "found" : "recent", rows: latestFirst(matching) }];
  else {
    const inside = new Set(here);
    groups = [{ id: "here", rows: inProjectOrder(here) }, { id: "other", rows: latestFirst(matching.filter(row => !inside.has(row))) }];
  }
  const total = groups.reduce((sum, group) => sum + group.rows.length, 0);
  let room = limit;
  const capped = groups.map(group => {
    const rows = group.rows.slice(0, Math.max(0, room));
    room -= rows.length;
    return { ...group, rows };
  }).filter(group => group.rows.length);
  return { groups: capped, total };
}
