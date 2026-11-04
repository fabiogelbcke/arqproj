// The portfolio (backend/web/portfolio_page.py): the carousel's arrows and count,
// and photos opened large. Without this script the page still works.
for (const carousel of document.querySelectorAll(".carousel")) {
  const track = carousel.querySelector(".track");
  const controls = carousel.querySelector(".controls");
  if (!track || !controls) continue;
  const slides = track.children;
  const count = controls.querySelector(".count b");
  const current = () => Math.round(track.scrollLeft / track.clientWidth);
  const go = (index) => {
    const target = (index + slides.length) % slides.length;
    const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
    track.scrollTo({ left: target * track.clientWidth, behavior: smooth ? "smooth" : "auto" });
  };
  controls.querySelector(".prev").addEventListener("click", () => go(current() - 1));
  controls.querySelector(".next").addEventListener("click", () => go(current() + 1));
  track.addEventListener("scroll", () => {
    count.textContent = String(current() + 1).padStart(2, "0");
  }, { passive: true });
  controls.hidden = false;
}

// A work's photos and videos open large over the page, one after another with
// the arrows, the keyboard or a swipe; a video plays only here. Without this
// script each link opens the photo or the video alone.
const lightbox = document.querySelector(".lightbox");
if (lightbox && lightbox.showModal) {
  const links = [...document.querySelectorAll("a.zoom")];
  const image = lightbox.querySelector("img");
  const video = lightbox.querySelector("video");
  const count = lightbox.querySelector(".count");
  let shown = 0;
  const stopVideo = () => {
    video.pause();
    video.removeAttribute("src");
    video.removeAttribute("poster");
    video.load(); // lets go of the file
  };
  const show = (index) => {
    shown = (index + links.length) % links.length;
    const link = links[shown];
    const label = link.querySelector("img:not(.backdrop)")?.alt ?? "";
    const film = link.classList.contains("film");
    stopVideo();
    image.hidden = film;
    video.hidden = !film;
    if (film) {
      image.removeAttribute("src");
      video.poster = link.dataset.poster;
      video.src = link.href;
      video.setAttribute("aria-label", label);
      video.play().catch(() => {}); // asked for with a click; a browser may still wait for one on the video
    } else {
      image.src = link.href;
      image.alt = label;
    }
    count.textContent = `${shown + 1} / ${links.length}`;
  };
  links.forEach((link, index) =>
    link.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey) return; // a new tab, as asked
      event.preventDefault();
      lightbox.showModal();
      show(index);
    }),
  );
  const single = links.length < 2;
  for (const button of lightbox.querySelectorAll(".prev, .next")) button.hidden = single;
  count.hidden = single;
  lightbox.querySelector(".prev").addEventListener("click", () => show(shown - 1));
  lightbox.querySelector(".next").addEventListener("click", () => show(shown + 1));
  lightbox.querySelector(".close").addEventListener("click", () => lightbox.close());
  // A click on the dark backdrop, not the photo, the video or a button, closes it.
  lightbox.addEventListener("click", (event) => event.target === lightbox && lightbox.close());
  lightbox.addEventListener("keydown", (event) => {
    if (event.target === video) return; // its own keys: ← → move within the video
    if (event.key === "ArrowLeft") show(shown - 1);
    if (event.key === "ArrowRight") show(shown + 1);
  });
  let start = null;
  lightbox.addEventListener("touchstart", (event) => {
    // On a video a swipe may be its timeline being dragged: the arrows move on.
    start = event.target === video ? null : event.touches[0].clientX;
  }, { passive: true });
  lightbox.addEventListener("touchend", (event) => {
    const moved = start === null ? 0 : event.changedTouches[0].clientX - start;
    if (Math.abs(moved) > 50) show(shown + (moved < 0 ? 1 : -1));
    start = null;
  });
  lightbox.addEventListener("close", () => {
    stopVideo();
    image.removeAttribute("src");
  });
}

// The mosaic format (the works' covers, or a work's images): in the
// order staff set them, left to right then down, in as many columns as fit; a
// work's images keep two on a phone. Without this, the stylesheet's columns
// fill top to bottom first.
// Every work's card, those a filtered address (`/?tipo=…`) hides too, taken
// before the mosaic leaves the hidden ones out of the page: the menu of types
// below shows them again.
const cards = [...document.querySelectorAll(".works > li, .mosaic > li")];
let relayMosaic = () => {};
for (const mosaic of document.querySelectorAll(".mosaic")) {
  const works = [...mosaic.children];
  const least = mosaic.classList.contains("posts") ? 2 : 1;
  const lay = (again = false) => {
    const width = mosaic.clientWidth;
    const count = width > 1020 ? 3 : width > 500 ? 2 : least;
    if (!again && mosaic.dataset.columns === String(count)) return;
    mosaic.dataset.columns = String(count);
    mosaic.replaceChildren();
    const columns = works.slice(0, count).map(() => {
      const column = document.createElement("li");
      column.className = "column";
      const list = document.createElement("ul");
      column.append(list);
      mosaic.append(column);
      return list;
    });
    // A work hidden by the menu of types stays out of the columns.
    works.filter((work) => !work.hidden).forEach((work, index) => columns[index % count].append(work));
  };
  lay();
  new ResizeObserver(() => lay()).observe(mosaic);
  if (!mosaic.classList.contains("posts")) relayMosaic = () => lay(true);
}

// The menu of types switches the works shown in place, as tabs, and keeps the
// address (`/?tipo=interiors`) so it can be shared and the back button works.
// Without this script each link reloads the page with that type.
const types = document.querySelector(".types");
if (types) {
  const links = [...types.querySelectorAll("a")];
  const key = (href) => new URL(href, location.href).searchParams.get("tipo");
  const show = (wanted) => {
    for (const link of links) {
      if (key(link.href) === wanted) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    for (const card of cards) card.hidden = wanted !== null && card.dataset.type !== wanted;
    relayMosaic();
  };
  links.forEach((link) =>
    link.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey) return; // a new tab, as asked
      event.preventDefault();
      const url = new URL(link.href);
      url.hash = "";
      history.pushState(null, "", url);
      show(key(link.href));
    }),
  );
  addEventListener("popstate", () => show(key(location.href)));
}
