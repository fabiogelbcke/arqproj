import posthog from "./posthog";

type LogAttributes = Record<string, string | number | boolean>;

/** Dedicated PostHog log channel; existing application logging remains local. */
export const posthogLog = {
  info(message: string, attributes: LogAttributes): void {
    posthog.logger.info(message, attributes);
  },
};
