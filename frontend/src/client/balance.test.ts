import { describe, expect, it } from "vitest";

import { SLACK, cardsToMove, inUse } from "./balance";

const GAP = 24;

describe("cardsToMove", () => {
  it("keeps the cards on the side when the columns are close", () => {
    // Main 600; side 300 + meeting 130 + sign-up 150 (+ gaps) = 628.
    expect(cardsToMove(600, 300, [130, 150], GAP)).toBe(0);
  });

  it("keeps them on the side when the side runs a little longer, up to the slack", () => {
    const side = 300 + 2 * GAP + 130 + 150;
    expect(cardsToMove(side - SLACK, 300, [130, 150], GAP)).toBe(0);
  });

  it("moves the meeting first when the side would run much longer", () => {
    // Main 250, side 628: moving the meeting (154 with its gap) leaves 404 against 474.
    expect(cardsToMove(250, 300, [130, 150], GAP)).toBe(1);
  });

  it("moves both when the main column is nearly empty", () => {
    // No description, few stages: main 60, side 728 with both cards.
    expect(cardsToMove(60, 400, [130, 150], GAP)).toBe(2);
  });

  it("doesn't move a card that would leave the main column the longer by more", () => {
    // Main 400, side 300 + a tall card (624 with its gap): moving it leaves 1024 against 300.
    expect(cardsToMove(400, 300, [600], GAP)).toBe(0);
  });

  it("moves nothing when there's nothing to move", () => {
    expect(cardsToMove(0, 900, [], GAP)).toBe(0);
  });
});

describe("inUse", () => {
  const card = (html: string) => {
    const element = document.createElement("div");
    element.innerHTML = html;
    document.body.append(element);
    return element;
  };

  it("is false for a card no one is using", () => {
    expect(inUse(card("<p>Próxima reunião</p><button>Adicionar à agenda</button>"))).toBe(false);
    expect(inUse(card('<input type="email" value="" />'))).toBe(false);
  });

  it("is true while an e-mail is typed or an editor holds values", () => {
    const signUp = card('<input type="email" />');
    signUp.querySelector("input")!.value = "ana@exemplo.com.br";
    expect(inUse(signUp)).toBe(true);
    expect(inUse(card('<textarea>Reunião de obra</textarea>'))).toBe(true);
  });

  it("is true while something in it has the focus", () => {
    const element = card("<button>Adicionar à agenda</button>");
    element.querySelector("button")!.focus();
    expect(inUse(element)).toBe(true);
  });
});
