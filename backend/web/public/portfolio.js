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

// The feed format's mosaic: the works in the order staff set them, left to
// right then down, in as many columns as fit. Without this, the stylesheet's
// columns fill top to bottom first.
const feed = document.querySelector(".feed");
if (feed) {
  const works = [...feed.children];
  const lay = () => {
    const width = feed.clientWidth;
    const count = width > 1020 ? 3 : width > 500 ? 2 : 1;
    if (feed.dataset.columns === String(count)) return;
    feed.dataset.columns = String(count);
    feed.replaceChildren();
    const columns = works.slice(0, count).map(() => {
      const column = document.createElement("li");
      column.className = "column";
      const list = document.createElement("ul");
      column.append(list);
      feed.append(column);
      return list;
    });
    works.forEach((work, index) => columns[index % count].append(work));
  };
  lay();
  new ResizeObserver(lay).observe(feed);
}
