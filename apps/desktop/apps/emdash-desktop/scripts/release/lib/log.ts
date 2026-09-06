const isCI = !!process.env.CI;

export function step(name: string): void {
  if (isCI) {
    console.log(`::group::${name}`);
  } else {
    console.log(`\n==> ${name}`);
  }
}

export function endStep(): void {
  if (isCI) {
    console.log('::endgroup::');
  }
}

export function info(msg: string): void {
  console.log(`    ${msg}`);
}

export function warn(msg: string): void {
  if (isCI) {
    console.log(`::warning::${msg}`);
  } else {
    console.warn(`⚠  ${msg}`);
  }
}

export function fail(msg: string): never {
  if (isCI) {
    console.error(`::error::${msg}`);
  } else {
    console.error(`✖  ${msg}`);
  }
  process.exit(1);
}
