import { describe, expect, it } from 'vitest';
import {
  byField,
  chainComparators,
  compareDates,
  compareNumbers,
  compareStrings,
} from './comparators';

describe('compareStrings', () => {
  it('sorts alphabetically', () => {
    const arr = ['Banana', 'apple', 'Cherry'];
    expect([...arr].sort(compareStrings)).toEqual(['apple', 'Banana', 'Cherry']);
  });

  it('returns 0 for equal strings', () => {
    expect(compareStrings('a', 'a')).toBe(0);
  });
});

describe('compareNumbers', () => {
  it('sorts ascending', () => {
    expect([3, 1, 2].sort(compareNumbers)).toEqual([1, 2, 3]);
  });
});

describe('compareDates', () => {
  it('sorts chronologically', () => {
    const d1 = new Date('2024-01-01');
    const d2 = new Date('2024-06-01');
    const d3 = new Date('2023-12-01');
    expect([d1, d2, d3].sort(compareDates)).toEqual([d3, d1, d2]);
  });
});

describe('byField', () => {
  interface Item {
    name: string;
    age: number;
    created: Date;
  }

  const items: Item[] = [
    { name: 'Charlie', age: 30, created: new Date('2024-03-01') },
    { name: 'Alice', age: 25, created: new Date('2024-01-01') },
    { name: 'Bob', age: 35, created: new Date('2024-02-01') },
  ];

  it('sorts by string field asc', () => {
    const sorted = [...items].sort(byField((i) => i.name));
    expect(sorted.map((i) => i.name)).toEqual(['Alice', 'Bob', 'Charlie']);
  });

  it('sorts by string field desc', () => {
    const sorted = [...items].sort(byField((i) => i.name, 'desc'));
    expect(sorted.map((i) => i.name)).toEqual(['Charlie', 'Bob', 'Alice']);
  });

  it('sorts by number field', () => {
    const sorted = [...items].sort(byField((i) => i.age));
    expect(sorted.map((i) => i.age)).toEqual([25, 30, 35]);
  });

  it('sorts by date field', () => {
    const sorted = [...items].sort(byField((i) => i.created));
    expect(sorted.map((i) => i.name)).toEqual(['Alice', 'Bob', 'Charlie']);
  });
});

describe('chainComparators', () => {
  interface Item {
    group: string;
    name: string;
  }

  const items: Item[] = [
    { group: 'B', name: 'Zebra' },
    { group: 'A', name: 'Mango' },
    { group: 'B', name: 'Apple' },
    { group: 'A', name: 'Banana' },
  ];

  it('applies comparators in order, breaking ties', () => {
    const cmp = chainComparators<Item>(
      byField((i) => i.group),
      byField((i) => i.name)
    );
    const sorted = [...items].sort(cmp);
    expect(sorted.map((i) => `${i.group}:${i.name}`)).toEqual([
      'A:Banana',
      'A:Mango',
      'B:Apple',
      'B:Zebra',
    ]);
  });

  it('returns 0 when all comparators agree', () => {
    const cmp = chainComparators(compareStrings, compareStrings);
    expect(cmp('a', 'a')).toBe(0);
  });
});
