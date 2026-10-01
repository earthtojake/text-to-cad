/**
 * What a terminal emulator writes back on its own, as opposed to what a person
 * typed. Pure and dependency-free: the terminal tab (renderer) and the pty
 * manager (main) both classify with it.
 *
 * xterm.js answers a program's queries through the same `onData` stream as
 * keystrokes: device attributes (`ESC[c` → `ESC[?1;2c`), a cursor position
 * report (`ESC[6n` → `ESC[<row>;<col>R`), a status report, a mode or window
 * report, a colour query (OSC 10/11/4), a DECRQSS reply, and focus in/out when
 * the program asked for them. None of them is input a person left half typed,
 * and one produced by replaying old scrollback answers a question the running
 * program never asked.
 */

const CSI_REPLY = String.raw`\x1b\[(?:[?>]?[\d;]*c|\??\d+;\d+R|\d*n|\??[\d;]+\$y|[\d;]+t|[IO])`;
const OSC_REPLY = String.raw`\x1b\](?:\d+;)+[^\x07\x1b]*(?:\x07|\x1b\\)`;
const DCS_REPLY = String.raw`\x1bP[^\x1b]*\x1b\\`;

const REPLIES = new RegExp(`^(?:${CSI_REPLY}|${OSC_REPLY}|${DCS_REPLY})+$`);

/** True when `data` is nothing but terminal-generated replies. */
export function isTerminalReply(data: string): boolean {
  return REPLIES.test(data);
}
