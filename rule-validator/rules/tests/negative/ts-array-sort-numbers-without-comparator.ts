// Negative corpus for ts-array-sort-numbers-without-comparator.

// 1. Sort with explicit comparator
export function f1(durations: number[]) {
  return durations.sort((a, b) => a - b);
}

// 2. Comparator with descending order
export function f2(prices: number[]) {
  return prices.sort((a, b) => b - a);
}

// 3. Sort of strings — variable name is `names` which is not in the regex
export function f3(names: string[]) {
  return names.sort();
}

// 4. Variable name `labels` — not a numeric collection name
export function f4(labels: string[]) {
  return labels.sort();
}

// 5. Comparator passed explicitly to durations.sort
export function f5(durations: number[]) {
  return durations.sort((a, b) => a - b);
}

// 6. Custom comparator
export function f6(amounts: number[]) {
  amounts.sort(myCmp);
  return amounts;
}
function myCmp(a: number, b: number) { return a - b; }

// 7. Array.from(new Set).sort with comparator
export function f7(durations: number[]) {
  return Array.from(new Set(durations)).sort((a, b) => a - b);
}

// 8. Variable name `tags` — not numeric family
export function f8(tags: string[]) {
  return tags.sort();
}

// 9. Variable name `items` — not in the allowlist
export function f9(items: number[]) {
  return items.sort();
}

// 10. toSorted with comparator
export function f10(numbers: number[]) {
  return numbers.sort((a, b) => a - b);
}

// 11. Sort with localeCompare-style comparator on strings
export function f11(words: string[]) {
  return words.sort((a, b) => a.localeCompare(b));
}

// 12. Variable name `entries` — not in allowlist
export function f12(entries: number[]) {
  return entries.sort();
}
