import { rendererCommands } from "../integrations";
import type { IntegrationReply } from "../../shared/ipc/integrations";
export const integrationHandlers = { integrations: { reply: (reply: IntegrationReply) => rendererCommands().reply(reply) } };
