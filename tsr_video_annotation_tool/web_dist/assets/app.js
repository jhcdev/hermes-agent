const app = document.querySelector("#app");
const canvas = document.querySelector("#annotation-canvas");
const status = document.querySelector("#status");
const frameLabel = document.querySelector("#frame-label");
const frameProgress = document.querySelector("#frame-progress");
const modes = [...document.querySelectorAll("[data-workflow]")];

const totalFrames = Number(app?.dataset.totalFrames || 1001);
let currentFrame = 1;
let workflow = "gt";

function updateFrame(nextFrame) {
  currentFrame = Math.min(Math.max(nextFrame, 1), totalFrames);
  frameLabel.textContent = `${currentFrame} / ${totalFrames}`;
  frameProgress.value = currentFrame;
  status.textContent = `${workflow.toUpperCase()} workflow ready on frame ${currentFrame}.`;
  drawGuide();
}

function setWorkflow(nextWorkflow) {
  workflow = nextWorkflow;
  modes.forEach((mode) => mode.classList.toggle("active", mode.dataset.workflow === workflow));
  updateFrame(currentFrame);
}

function drawGuide() {
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#121a25";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.strokeStyle = workflow === "gt" ? "#2dd4bf" : "#f59e0b";
  context.lineWidth = 4;
  context.strokeRect(352, 198, 360, 220);
  context.fillStyle = "#ffffff";
  context.font = "28px system-ui";
  context.fillText(workflow === "gt" ? "Draw GT boxes and polygons" : "Review tracked delta changes", 36, 54);
}

modes.forEach((mode) => {
  mode.addEventListener("click", () => setWorkflow(mode.dataset.workflow));
});

document.addEventListener("keydown", (event) => {
  if (event.key === "ArrowRight") updateFrame(currentFrame + 1);
  if (event.key === "ArrowLeft") updateFrame(currentFrame - 1);
  if (event.key.toLowerCase() === "g") setWorkflow("gt");
  if (event.key.toLowerCase() === "d") setWorkflow("delta");
});

updateFrame(currentFrame);
