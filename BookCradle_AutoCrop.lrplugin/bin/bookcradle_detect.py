import os
import sys
import cv2
import json
import math
import rawpy
import argparse
import traceback
import numpy as np

# Default fallback path in case of argument parsing or imports fail
out_path = "results.ndjson"

def main():
    global out_path
    
    # Setup argument parsing
    ap = argparse.ArgumentParser()
    ap.add_argument("--dng-list", required=True, help="Text file with DNG paths")
    ap.add_argument("--mode", default="inside", help="Crop mode: inside or outside")
    ap.add_argument("--strategy", default="average", help="Inside crop strategy: tight, average, max")
    ap.add_argument("--margin", type=float, default=0.0, help="Per-side margin (if outside)")
    ap.add_argument("--out", default="results.ndjson", help="NDJSON output path")
    args = ap.parse_args()
    
    out_path = args.out

    try:
        # Open the text file provided in --dng-list, read each line, 
        # strip whitespace, and create a list called "paths".
        with open(args.dng_list, "r", encoding="utf-8") as f:
            paths = [ln.strip() for ln in f if ln.strip()]
        if not paths:
            sys.exit(0)

        global_W, global_H = 0, 0
        pre_data = {}

        # ==========================================
        # PASS 1: PAPER AREA & 60% WALKDOWN
        # ==========================================
        # Start this loop for each expected image. 
        # If an image doesn't exist, lacks a preview, or OpenCV fails to read it, log an error and skip.
        for i, path in enumerate(paths):
            try:
                # Command rawpy to extract the embedded preview from the DNG.
                # This bypasses the need for exporting temporary JPEGs from Lightroom.
                with rawpy.imread(path) as raw:
                    try:
                        thumb = raw.extract_thumb()
                        if thumb.format != rawpy.ThumbFormat.JPEG:
                            pre_data[path] = {"error": "not_jpeg_preview"}
                            continue
                    except rawpy.LibRawNoThumbnailError:
                        pre_data[path] = {"error": "no_preview"}
                        continue

                # Decode the image directly to grayscale and ignore orientation metadata.
                # This keeps the image in the DNG's native orientation, which Lightroom uses to map the coordinate plane.
                img_array = np.frombuffer(thumb.data, np.uint8)
                gray = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE | cv2.IMREAD_IGNORE_ORIENTATION)
                
                if gray is None:
                    pre_data[path] = {"error": "decode_failed"}
                    continue
                    
            except Exception as e:
                pre_data[path] = {"error": f"rawpy_error: {str(e)}"}
                continue

            H, W = gray.shape[:2]
            global_H, global_W = H, W 

            # 1. Define the Paper Area
            # Apply Gaussian Blur to remove noise.
            # Finds the boundaries of the main paper/document. Logs fallback dimensions if nothing is found.
            blur = cv2.GaussianBlur(gray, (15, 15), 0)
            _, paper_bin = cv2.threshold(blur, 100, 255, cv2.THRESH_BINARY)
            kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
            paper_solid = cv2.morphologyEx(paper_bin, cv2.MORPH_CLOSE, kernel_close)
            blob_cnts, _ = cv2.findContours(paper_solid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if blob_cnts:
                main_blob = max(blob_cnts, key=cv2.contourArea)
                px, py, pw, ph = cv2.boundingRect(main_blob)
            else:
                px, py, pw, ph = int(W*0.1), int(H*0.1), int(W*0.8), int(H*0.8)

            # 2. Edge Detection inside the paper boundaries
            roi_gray = gray[py:py+ph, px:px+pw]
            edges = cv2.Canny(roi_gray, 50, 150)

            # 3. Scans image from top down to find the glass gutter.
            gutter_y_raw = py + ph # Failsafe default
            
            start_y = int(ph * 0.10)
            end_y = int(ph * 0.95)
            window_h = max(int(pw * 0.03), 5) 

            for y in range(start_y, end_y):
                window = edges[y : y + window_h, :]
                collapsed = np.max(window, axis=0) 
                edge_span = np.sum(collapsed == 255)
                
                if edge_span >= (pw * 0.60):
                    gutter_y_raw = py + y 
                    break

            pre_data[path] = {
                "error": None, "px": px, "py": py, "pw": pw, "ph": ph,
                "gutter_y_raw": gutter_y_raw
            }

        # ==========================================
        # PASS 1.5: GUTTER LOCATION CONSENSUS
        # ==========================================
        # Calculate the median gutter line across the entire batch to ignore outliers.
        valid_gutters = [data["gutter_y_raw"] for path, data in pre_data.items() if not data.get("error")]
        
        if valid_gutters:
            median_gutter = np.median(valid_gutters)
        else:
            median_gutter = global_H * 0.85 
            
        outlier_thresh = global_H * 0.03 
        
        for path, data in pre_data.items():
            if not data.get("error"):
                if abs(data["gutter_y_raw"] - median_gutter) > outlier_thresh:
                    data["gutter_y"] = int(median_gutter)
                else:
                    data["gutter_y"] = data["gutter_y_raw"]

        # ==========================================
        # PASS 2: Straighten and Center Crop Box
        # ==========================================
        # Second pass over the images to calculate angle and centering of concensus crop box.
        page_data = []
        
        for i, path in enumerate(paths):
            p_data = pre_data.get(path, {"error": "unknown"})
            if p_data.get("error"):
                page_data.append({"error": p_data["error"], "path": path, "index": i + 1})
                continue

            # Read the file again to execute pass 2 logic
            with rawpy.imread(path) as raw:
                thumb = raw.extract_thumb()
            img_array = np.frombuffer(thumb.data, np.uint8)
            gray = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE | cv2.IMREAD_IGNORE_ORIENTATION)

            px, py, pw, ph = p_data["px"], p_data["py"], p_data["pw"], p_data["ph"]
            gutter_y = p_data["gutter_y"]

            # Convert grayscale to binary black and white.
	        # Take consensus gutter location from pass 1 and black out everything below it.
            _, paper_thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            paper_thresh[gutter_y:, :] = 0  
            
	        # Close holes in the white pixel area to define the extent of the page area.
            kernel_close_iso = cv2.getStructuringElement(cv2.MORPH_RECT, (51, 51))
            paper_solid_iso = cv2.morphologyEx(paper_thresh, cv2.MORPH_CLOSE, kernel_close_iso)
            cnts, _ = cv2.findContours(paper_solid_iso, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
	        # Place a seed in the center of the page area.
            seed_x = int(global_W / 2)
            seed_y = int(py + ((gutter_y - py) / 2))

            target_page_contour = None
            for c in cnts:
                if cv2.pointPolygonTest(c, (float(seed_x), float(seed_y)), False) >= 0:
                    target_page_contour = c
                    break

            # Check page contours to ensure seed is placed on a page.        
            if target_page_contour is None and cnts:
                target_page_contour = max(cnts, key=cv2.contourArea)

            found_paper = False
            page_angle = 0.0
            
            if target_page_contour is not None and cv2.contourArea(target_page_contour) > (global_W * global_H * 0.05):
                px_i, py_i, pw_i, ph_i = cv2.boundingRect(target_page_contour)
                page_cx = px_i + pw_i / 2.0
                page_cy = py_i + ph_i / 2.0
                found_paper = True
                
                rect = cv2.minAreaRect(target_page_contour)
                (_, _), _, pa = rect
                if pa < -45: pa += 90
                if pa > 45: pa -= 90
                elif pa < -45: pa += 90
                if abs(pa) < 15:
                    page_angle = float(pa)
            else:
                px_i, py_i, pw_i, ph_i = int(global_W * 0.15), int(global_H * 0.05), int(global_W * 0.7), max(10, int(gutter_y - global_H * 0.05))
                page_cx = px_i + pw_i / 2.0
                page_cy = py_i + ph_i / 2.0

            # Create safe zone to look for page features, shrink edges inward 1.5% to avoid book/page edges.
            safe_zone = np.zeros_like(gray)
            if target_page_contour is not None:
                cv2.drawContours(safe_zone, [target_page_contour], -1, 255, thickness=cv2.FILLED)
                erode_size = max(int(global_W * 0.015), 5) 
                erode_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (erode_size, erode_size))
                safe_zone = cv2.erode(safe_zone, erode_kernel, iterations=1)
            else:
                cv2.rectangle(safe_zone, (px_i, py_i), (px_i + pw_i, py_i + ph_i), 255, -1)

            # Adapive thresholding to create black and white image from grayscale.
	        # Apply safe zone to the thresholded image. 
            adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 61, 15)
            text_in_safe_zone = cv2.bitwise_and(adaptive, safe_zone)
            
            # Use a tight kernel to bridge lines of text together into larger blocks.
            tight_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
            tight_closed = cv2.morphologyEx(text_in_safe_zone, cv2.MORPH_CLOSE, tight_kernel)

	        # Find boundaries of all blocks. 
            content_cnts, _ = cv2.findContours(tight_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            valid_cnts = [c for c in content_cnts if cv2.contourArea(c) > 500]
            
            has_content = False
            content_angle = 0.0
            
            if valid_cnts:
                has_content = True

	            # Draw bounding box around all blocks, and calculate center of the bounding box.
                all_pts = np.vstack(valid_cnts)
                tx, ty, tw, th = cv2.boundingRect(all_pts)
                content_cx = tx + tw / 2.0
                content_cy = ty + th / 2.0

                # Run a larger kernel over content to blend into larger blocks of text/content.
                macro_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (51, 51))
                macro_closed = cv2.morphologyEx(text_in_safe_zone, cv2.MORPH_CLOSE, macro_kernel)
                macro_cnts, _ = cv2.findContours(macro_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                if macro_cnts:
                    # Find the angle of the largest block in the page area. 
                    largest_macro = max(macro_cnts, key=cv2.contourArea)
                    
                    rect = cv2.minAreaRect(largest_macro)
                    (_, _), (rw, rh), ra = rect
                    
                    # Normalize the angle regardless of orientation
                    if rw < rh:
                        ra += 90
                    if ra > 45: ra -= 90
                    elif ra < -45: ra += 90
                    
                    # Only accept angles that are less than 15 degrees either way.
		            # Angles greater than 15 degrees are assumed to be incorrect, and are thus discarded.
                    if abs(ra) < 15:
                        content_angle = float(ra)
                else:
                    content_angle = 0.0
            else:
                tw, th = 0, 0
                content_cx, content_cy = page_cx, page_cy

            if args.mode == "outside":
                angle = page_angle
            else:
                if has_content:
                    angle = content_angle
                else:
                    angle = page_angle

            if not found_paper:
                angle = 0.0

            page_data.append({
                "error": None, "path": path, "index": i + 1,
                "found_paper": found_paper,
                "has_content": has_content,
                "page_cx": page_cx, "page_cy": page_cy,
                "content_cx": content_cx, "content_cy": content_cy,
                "px": px_i, "py": py_i, "pw": pw_i, "ph": ph_i,
                "tw": tw, "th": th,
                "angle": angle
            })

        # ==========================================
        # FINAL CROP CONSENSUS & OUTPUT
        # ==========================================
        # Compare all pages in the batch to find uniform crop dimensions that fit everyone.
        valid_pages = [d for d in page_data if not d["error"]]
        if not valid_pages:
            sys.exit(0)

        valid_papers = [d for d in valid_pages if d["found_paper"]]
        if valid_papers:
            master_cx = np.median([d["page_cx"] for d in valid_papers])
            master_cy = np.median([d["page_cy"] for d in valid_papers])
            master_pw = np.median([d["pw"] for d in valid_papers])
            master_ph = np.median([d["ph"] for d in valid_papers])
        else:
            master_cx, master_cy = global_W / 2.0, global_H / 2.0
            master_pw, master_ph = global_W * 0.7, global_H * 0.7

        for d in valid_pages:
            if not d["found_paper"]:
                d["page_cx"] = master_cx
                d["page_cy"] = master_cy
                d["content_cx"] = master_cx
                d["content_cy"] = master_cx
                d["pw"] = master_pw
                d["ph"] = master_ph
                d["px"] = int(master_cx - master_pw / 2.0)
                d["py"] = int(master_cy - master_ph / 2.0)
                d["angle"] = 0.0 

        master_cy_offset = 0.0

	    # Id "valid" content area of pages
        if args.mode == "inside":
            valid_content_pages = [d for d in valid_pages if d["has_content"]]
            
            if valid_content_pages:
                max_tw = max([d["tw"] for d in valid_content_pages])
                max_th = max([d["th"] for d in valid_content_pages])
            else:
                max_tw, max_th = master_pw * 0.5, master_ph * 0.5

            # Add 2% buffer around the text. This is minimum crop size.
            text_pad_px = min(master_pw, master_ph) * 0.02
            min_target_w = max_tw + (text_pad_px * 2)
            min_target_h = max_th + (text_pad_px * 2)

            # Add 2% buffer inward from paper edge. This is maximum crop size.
            min_pw = min([d["pw"] for d in valid_papers]) if valid_papers else master_pw
            min_ph = min([d["ph"] for d in valid_papers]) if valid_papers else master_ph
            
            safe_max_w = min_pw - (text_pad_px * 2)
            safe_max_h = min_ph - (text_pad_px * 2)

            # Ensure text bounding box is smaller than paper area.
            min_target_w = min(min_target_w, safe_max_w)
            min_target_h = min(min_target_h, safe_max_h)

            # Apply crop strategy selected in UI.
            if args.strategy == "max":
                final_target_w = safe_max_w
                final_target_h = safe_max_h
            elif args.strategy == "average":
                final_target_w = (min_target_w + safe_max_w) / 2.0
                final_target_h = (min_target_h + safe_max_h) / 2.0
            else: # "tight"
                final_target_w = min_target_w
                final_target_h = min_target_h
            
            final_target_w = max(final_target_w, 100)
            final_target_h = max(final_target_h, 100)

        else: 
            # Margin Application
            # Calculate percentage as pixels, based on the short edge of the *master page size*.
            pad_px = min(master_pw, master_ph) * args.margin
            final_target_w = master_pw + (pad_px * 2)
            final_target_h = master_ph + pad_px
            master_cy_offset = -(pad_px / 2.0)

        results = []
        for data in page_data:
            if data["error"]:
                results.append({"index": data["index"], "path": data["path"], "error": data["error"]})
                continue

            if args.mode == "inside":
                eff_cx = data["content_cx"]
                eff_cy = data["content_cy"]
            else:
                eff_cx = data["page_cx"]
                eff_cy = data["page_cy"] + master_cy_offset

	        # Draft crop box boundaries
            left   = eff_cx - (final_target_w / 2)
            right  = eff_cx + (final_target_w / 2)
            top    = eff_cy - (final_target_h / 2)
            bottom = eff_cy + (final_target_h / 2)

            # Check that the crop box is inside the bounds of the page's edges that were found earlier.
	        # If not, shift crop box to stay inside bounds.
            if args.mode == "inside":
                px, py, pw, ph = data["px"], data["py"], data["pw"], data["ph"]
                if left < px:
                    shift = px - left
                    left += shift
                    right += shift
                if right > px + pw:
                    shift = right - (px + pw)
                    left -= shift
                    right -= shift
                if top < py:
                    shift = py - top
                    top += shift
                    bottom += shift
                if bottom > py + ph:
                    shift = bottom - (py + ph)
                    top -= shift
                    bottom -= shift

            # Recalculate the center point in case previous step moved the box
            eff_cx = left + (final_target_w / 2)
            eff_cy = top + (final_target_h / 2)

            # Compensation for Lightroom's (what I assume is bugged) crop and rotation application. 
            # Using the applyDevelopSettings command in the Lightroom SDK to apply an angle will 
            # distort the crop box's width and height.
            # I determined the distortion is equal to the inverse of the function below.
            # We use the function below to calculate the width and height that, 
            # when distorted by applyDevelopSettings, will become the accurate width and height.
            theta = math.radians(data["angle"]) 
            cos_t = math.cos(theta)
            sin_t = math.sin(theta)

            send_w = final_target_w * cos_t - final_target_h * sin_t
            send_h = final_target_h * cos_t + final_target_w * sin_t

            # Safeguard to prevent crop box from inverting.
            send_w = max(abs(send_w), final_target_w * 0.4)
            send_h = max(abs(send_h), final_target_h * 0.4)

            # Overwrite old left/right/top/bottom variables with compensated ones
            left   = eff_cx - (send_w / 2)
            right  = eff_cx + (send_w / 2)
            top    = eff_cy - (send_h / 2)
            bottom = eff_cy + (send_h / 2)

	        # Make sure crop boxes are inside image bounds.
            left   = max(0, left)
            right  = min(global_W, right)
            top    = max(0, top)
            bottom = min(global_H, bottom)

            results.append({
                "index":  data["index"],
                "path":   data["path"],
                "left":   left / global_W,
                "right":  right / global_W,
                "top":    top / global_H,
                "bottom": bottom / global_H,
                "angle":  data["angle"]
            })

        # Write results list for each image to an ndjson file that will be passed back to Lightroom
        with open(args.out, "w", encoding="utf-8") as out:
            for r in results:
                out.write(json.dumps(r) + "\n")

    except Exception:
        # Catch runtime errors during detection and write the traceback to the JSON
        # so the Lightroom Lua plugin can read it and display a helpful dialog to the user.
        error_data = {"fatal_error": traceback.format_exc()}
        with open(out_path, "w", encoding="utf-8") as out:
            out.write(json.dumps(error_data) + "\n")
        sys.exit(0)

if __name__ == "__main__":
    # Ensure OpenCV optimizations are set before running main
    try:
        cv2.setUseOptimized(True)
    except (NameError, AttributeError):
        pass
    main()