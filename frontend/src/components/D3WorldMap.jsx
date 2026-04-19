import React, { useRef, useEffect } from "react";
import * as d3 from "d3";
import * as topojson from "topojson-client";

export function D3WorldMap({ events, boms }) {
  const svgRef = useRef();
  
  useEffect(() => {
    fetch('https://unpkg.com/world-atlas@2.0.2/countries-110m.json')
      .then(r => r.json())
      .then(world => {
         const countries = topojson.feature(world, world.objects.countries).features;
         const svg = d3.select(svgRef.current);
         svg.selectAll("*").remove();

         const node = svg.node();
         if (!node) return;
         const width = node.getBoundingClientRect().width;
         const height = node.getBoundingClientRect().height;

         const projection = d3.geoNaturalEarth1()
            .scale(width / 5.5)
            .translate([width / 2, height / 2 + 50]);
         const path = d3.geoPath().projection(projection);

         const g = svg.append("g");

         g.selectAll("path.country")
            .data(countries)
            .enter().append("path")
            .attr("class", "country")
            .attr("d", path)
            .attr("fill", "var(--glass-thick-bg)")
            .attr("stroke", "rgba(0,0,0,0.06)")
            .attr("stroke-width", 1)
            .transition().duration(1000)
            .attr("fill", d => {
              // Highlight China (ISO 156) if there are events
              if(events.length > 0 && d.id === "156") return "rgba(209,67,67,0.15)";
              return "rgba(255,255,255,0.7)";
            });

         const usCoords = projection([-95.7, 37.0]);
         const cnCoords = projection([104.1, 35.8]); // China
         const twCoords = projection([120.9, 23.6]); // Taiwan
         
         if (events.length > 0 && usCoords && cnCoords && twCoords) {
             const defs = svg.append("defs");
             const filter = defs.append("filter").attr("id", "glow");
             filter.append("feGaussianBlur").attr("stdDeviation", "3").attr("result", "coloredBlur");
             const feMerge = filter.append("feMerge");
             feMerge.append("feMergeNode").attr("in", "coloredBlur");
             feMerge.append("feMergeNode").attr("in", "SourceGraphic");

             const drawArc = (source, target, color) => {
               const arc = d3.line().curve(d3.curveBasis)([
                 source,
                 [ (source[0]+target[0])/2, Math.min(source[1], target[1]) - 150 ],
                 target
               ]);
               
               const line = svg.append("path")
                  .attr("d", arc)
                  .attr("fill", "none")
                  .attr("stroke", color)
                  .attr("stroke-width", 2)
                  .attr("stroke-dasharray", "6,4")
                  .attr("opacity", 0.8)
                  .style("filter", "url(#glow)");

               const totalLength = line.node().getTotalLength();
               line
                 .attr("stroke-dasharray", totalLength + " " + totalLength)
                 .attr("stroke-dashoffset", totalLength)
                 .transition()
                 .duration(2000)
                 .attr("stroke-dashoffset", 0)
                 .on("end", function() {
                    d3.select(this)
                      .attr("stroke-dasharray", "6,4")
                      .style("animation", "dash 20s linear infinite");
                 });
             };

             drawArc(cnCoords, usCoords, "var(--sev-critical)");
             drawArc(twCoords, usCoords, "var(--domain-reshore)");

             const drawPulse = (coords, color) => {
               svg.append("circle")
                  .attr("cx", coords[0]).attr("cy", coords[1])
                  .attr("r", 4).attr("fill", color)
                  .append("animate")
                  .attr("attributeName", "r")
                  .attr("values", "4;12;4")
                  .attr("dur", "2s")
                  .attr("repeatCount", "indefinite");
               svg.append("circle")
                  .attr("cx", coords[0]).attr("cy", coords[1])
                  .attr("r", 4).attr("fill", color)
                  .append("animate")
                  .attr("attributeName", "opacity")
                  .attr("values", "1;0;1")
                  .attr("dur", "2s")
                  .attr("repeatCount", "indefinite");
             };

             drawPulse(cnCoords, "var(--sev-critical)");
             drawPulse(twCoords, "var(--domain-reshore)");
             drawPulse(usCoords, "var(--fg-1)"); // US destination hub
         }
      });
  }, [events, boms]);

  return (
    <>
      <style>{`@keyframes dash { to { stroke-dashoffset: -1000; } }`}</style>
      <svg ref={svgRef} style={{width:'100%', height:'100%', pointerEvents:'none'}}/>
    </>
  );
}
