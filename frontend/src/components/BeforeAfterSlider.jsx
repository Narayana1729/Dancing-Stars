import React, { useState } from "react";

export default function BeforeAfterSlider({ beforeImg, afterImg, beforeDate, afterDate, locationLabel }) {
  const [sliderPosition, setSliderPosition] = useState(50);
  const [loaded, setLoaded] = useState({ before: false, after: false });
  const [failed, setFailed] = useState({ before: false, after: false });
  const mark = (setter, key) => () => setter((s) => ({ ...s, [key]: true }));
  const anyFailed = failed.before || failed.after;
  const loading = !anyFailed && !(loaded.before && loaded.after);

  const handleSliderChange = (e) => {
    setSliderPosition(e.target.value);
  };

  return (
    <div className="relative w-full aspect-[1024/368] min-h-[320px] overflow-hidden bg-[#23262b] border border-slate-800 select-none">
      {/* Before Image (Base Layer - Right Side) */}
      <img
        src={beforeImg}
        alt="Pre-Event Satellite View"
        onLoad={mark(setLoaded, "before")}
        onError={mark(setFailed, "before")}
        className="absolute inset-0 w-full h-full object-cover"
        draggable={false}
      />

      {/* Before Date Overlay (Bottom Left style of SVS) */}
      <div className="absolute bottom-6 left-6 z-10 pointer-events-none drop-shadow-[0_2px_4px_rgba(0,0,0,0.9)]">
        <p className="text-white font-sans text-2xl font-light tracking-wide whitespace-pre-line">
          {beforeDate}
        </p>
      </div>

      {/* Map Scale Bar (Bottom Left) */}
      <div className="absolute bottom-3 left-6 z-10 pointer-events-none flex items-center space-x-2 opacity-80">
        <div className="text-[10px] text-white font-mono">0</div>
        <div className="w-16 h-[2px] bg-white relative">
          <div className="absolute top-0 left-0 h-1 w-[1px] bg-white -translate-y-0.5"></div>
          <div className="absolute top-0 left-1/2 h-1 w-[1px] bg-white -translate-y-0.5"></div>
          <div className="absolute top-0 right-0 h-1 w-[1px] bg-white -translate-y-0.5"></div>
        </div>
        <div className="text-[10px] text-white font-mono">10 km</div>
      </div>

      {/* After Image (Clipped Layer - Left Side) */}
      <div
        className="absolute inset-0 overflow-hidden"
        style={{ clipPath: `polygon(0 0, ${sliderPosition}% 0, ${sliderPosition}% 100%, 0 100%)` }}
      >
        <img
          src={afterImg}
          alt="Post-Event Satellite View"
          onLoad={mark(setLoaded, "after")}
          onError={mark(setFailed, "after")}
          className="absolute inset-0 w-full h-full object-cover max-w-none"
          style={{ width: "100%", height: "100%" }}
          draggable={false}
        />

        {/* Location Label (Top Left of After View, like 'Chókwè') */}
        {locationLabel && (
          <div className="absolute top-8 left-8 z-10 pointer-events-none drop-shadow-[0_4px_8px_rgba(0,0,0,0.9)]">
            <h2 className="text-white font-serif text-4xl tracking-wider font-normal italic">
              {locationLabel}
            </h2>
          </div>
        )}

        {/* After Date Overlay (Bottom Right style of SVS) */}
        <div className="absolute bottom-6 right-6 z-10 pointer-events-none text-right drop-shadow-[0_2px_4px_rgba(0,0,0,0.9)]">
          <p className="text-white font-sans text-2xl font-light tracking-wide whitespace-pre-line">
            {afterDate}
          </p>
        </div>
      </div>

      {/* Divider: thin white line spanning the full image height, chevrons on either side */}
      <div
        className="absolute top-0 bottom-0 w-[2px] bg-white z-20 pointer-events-none -translate-x-1/2"
        style={{ left: `${sliderPosition}%` }}
      >
        <svg className="absolute top-1/2 -translate-y-1/2 right-[10px] w-3 h-3 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 1 3 6l5 5" /></svg>
        <svg className="absolute top-1/2 -translate-y-1/2 left-[10px] w-3 h-3 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m4 1 5 5-5 5" /></svg>
      </div>

      {(loading || anyFailed) && (
        <div role={anyFailed ? "alert" : "status"} className="absolute inset-0 z-10 flex items-center justify-center bg-[#23262b]/90 px-6 text-center text-sm text-slate-200">
          {anyFailed ? "One or both images could not be loaded. Check your connection or the image source." : "Loading imagery…"}
        </div>
      )}

      {/* Invisible Range Input for Dragging */}
      <input
        type="range"
        min="0"
        max="100"
        value={sliderPosition}
        onChange={handleSliderChange}
        aria-label="Before/after slider"
        className="absolute inset-0 w-full h-full opacity-0 cursor-ew-resize z-30"
      />
    </div>
  );
}
