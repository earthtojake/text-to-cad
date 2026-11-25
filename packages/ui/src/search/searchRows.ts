import { filterModels, type LibraryModel } from "../library/ModelLibrary.js";
import { lastActivity } from "../lib/age.js";

/** How many rows the search draws at most; past it, a line says how many more there are. */
export const SEARCH_LIMIT = 50;

/** The project a row's document is in, as the search names it; null, a standalone document. */
export interface SearchProject { id: string; name: string }
/** One document the search lists: the row of it, its key (one row a document) and its project. */
export interface SearchRow<Model extends LibraryModel = LibraryModel> {
  key: string;
  model: Model;
  project: SearchProject | null;
}
/**
 * A group of rows, in the order drawn: `here`, the project of the document on screen ("In <project>"); `other`, the
 * library's other documents, under "Other projects"; `recent`, the latest documents where nothing is typed and the
 * document on screen is in no project; `found`, what a search finds where it is in none (one list, no heading).
 */
export interface SearchGroup<Model extends LibraryModel = LibraryModel> {
  id: "here" | "other" | "recent" | "found";
  rows: SearchRow<Model>[];
}

const slashed = (path: string) => String(path || "").replace(/\\/g, "/").replace(/\/+$/, "");
/** A document's key: its id where the host names one, else its path. */
export const rowKey = (model: LibraryModel) => model.id || slashed(model.path);

const latestFirst = <Model extends LibraryModel>(models: readonly Model[]) => models.map((model, index) => ({ model, index }))
  .sort((a, b) => (lastActivity(b.model) ?? 0) - (lastActivity(a.model) ?? 0) || a.index - b.index).map(({ model }) => model);

/**
 * What the search shows for `query`, grouped, at most `limit` rows in all (`total`: how many there are).
 *
 * - With a project on screen (`project`), `here` is what its host answered of it (`here`): with nothing typed, the files
 *   of the folder the document on screen is in, in that folder's order; typed, every file below the project's root that
 *   holds every word, as the host found them. Then, typed, the library's documents of other projects or of none that
 *   hold every word in a name or a path (`filterModels`), the latest first.
 * - With none, the library's documents: the latest with nothing typed, else those that hold every word, the latest first.
 *
 * The words narrow `here` as well, so an answer for fewer words stands until the one for these arrives.
 */
export function searchGroups<Model extends LibraryModel>({ list, here = null, names = new Map(), query, project = null, limit = SEARCH_LIMIT }: {
  /** The library's documents (`list()`). */
  list: readonly Model[];
  /** The host's rows of the project on screen; null while there are none. */
  here?: readonly Model[] | null;
  /** The projects' names, by id. */
  names?: ReadonlyMap<string, string>;
  query: string;
  project?: SearchProject | null;
  limit?: number;
}): { groups: SearchGroup<Model>[]; total: number } {
  const typed = query.trim().length > 0;
  const rowOf = (model: Model, own: SearchProject | null = null): SearchRow<Model> => ({ key: rowKey(model), model,
    project: own ?? (model.project && names.has(model.project) ? { id: model.project, name: names.get(model.project)! } : null) });
  let groups: SearchGroup<Model>[];
  if (project) {
    const inside = filterModels(here ?? [], query).map(model => rowOf(model, project));
    const keys = new Set(inside.flatMap(row => [row.key, slashed(row.model.path)]));
    const others = typed ? latestFirst(filterModels(list, query).filter(model => model.project !== project.id
      && !keys.has(rowKey(model)) && !keys.has(slashed(model.path)))).map(model => rowOf(model)) : [];
    groups = [{ id: "here", rows: inside }, { id: "other", rows: others }];
  } else groups = [{ id: typed ? "found" : "recent", rows: latestFirst(typed ? filterModels(list, query) : list).map(model => rowOf(model)) }];
  const total = groups.reduce((sum, group) => sum + group.rows.length, 0);
  let room = limit;
  const capped = groups.map(group => {
    const rows = group.rows.slice(0, Math.max(0, room));
    room -= rows.length;
    return { ...group, rows };
  }).filter(group => group.rows.length);
  return { groups: capped, total };
}
