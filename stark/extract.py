"""
Created on Fri Aug  9 22:33:50 2019

@author: Alexis Brandeker (Initial Version)
@author: Jayshil A. Patel (Modified to use with data cube)
"""
import numpy as np
from multiprocessing import Pool
from scipy.interpolate import LSQUnivariateSpline, LSQBivariateSpline
import warnings
import time

def aperture_extract(frame, variance, ord_pos, ap_rad, uniform = False):
    """ Simple aperture extraction of the spectrum

    Given the 2D `frame` of the data, and its `variance`, this function
    extracts spectrum by simply adding up values of pixels along slit.

    Parameters
    ----------
    frame : ndarray
        2D data frame from which the spectrum is to be extracted
    variance : ndarray
        The noise image of the same format as frame, specifying
        the variance of each pixel.
    ord_pos : ndarray
        Array defining position of the trace
    ap_rad : float
        Radius of the aperture around the order position
    uniform : bool, optional
        Boolean on whether the slit is uniformally lit or not.
        If not then it will simply sum up counts in the aperture
        else average the counts and multiply by slit-length.
        Default is False.

    Returns
    -------
    spec : ndarray
        Array containing extracted spectrum for each order and each column.
    var : ndarray
        Variance array for `spec`, the same shape as `spec`.
    """
    nslitpix = ap_rad*2
    ncols = frame.shape[1]
    spec = np.zeros(ncols)
    var = np.zeros(ncols)

    for col in range(ncols):
        if ord_pos[col] < 0 or ord_pos[col] >= frame.shape[0]:
            continue
        i0 = int(round(ord_pos[col] - ap_rad))
        i1 = int(round(ord_pos[col] + ap_rad))

        if i0 < 0:
            i0 = 0
        if i1 >= frame.shape[0]:
            i1 = frame.shape[0] - 1
        if uniform:
            spec[col] = np.mean(frame[i0:i1,col])*nslitpix
            var[col] = np.mean(variance[i0:i1,col])*nslitpix
        else:
            spec[col] = np.sum(frame[i0:i1,col])
            var[col] = np.sum(variance[i0:i1,col])
    return spec, var

def flux_coo(frame, variance, ord_pos, ap_rad):
    """ To produce pixel list with source coordinates
    
    Given a 3D data cube, this function gives array with coordinates
    (distace from order position), their flux and variances.
    This information is to be used when producing PSFs.
    This function works for single order and all columns.

    Parameters
    ----------
    frame: ndarray
        3D array containing data, [nints, nrows, ncols]
    variance : ndarray
        3D array as same size as `frame` containing variace of the data.
    ord_pos : ndarray
        2D array, with shape [nints, ncols] contaning pixel positions of order
    ap_rad : float
        Aperture radius
    
    Returns
    -------
    pix_array : ndarray
        Array with columns coordinate (in form of distance from order
        positions), flux and variance. Approx. of size [2*ap_rad*ncols*nints, 3]
    col_array_pos : ndarray
        Array with column's index in pix_array along with aperture size.
        This is used to be able to pick data from desired columns. E.g., if 
        the data in pix_array from columns 100 to 300 are desired, those correspond
        to indices col_array_pos[i,100,0] to col_array_pos[i,300,0] 
        for i-th integration in the pix_array.
    """
    nints = frame.shape[0]
    ncols = frame.shape[2]
    
    col_array_pos = np.zeros((nints, ncols, 2), dtype=int) # position and length in array
    pix_list = []
    col_pos = 0

    for integration in range(nints):
        for col in range(ncols):
            col_array_pos[integration, col, 0] = col_pos

            if ord_pos[integration, col] < 0 or ord_pos[integration, col] >= frame.shape[1]:
                continue
            i0 = int(round(ord_pos[integration, col] - ap_rad))
            i1 = int(round(ord_pos[integration, col] + ap_rad))

            if i0 < 0:
                i0 = 0
            if i1 >= frame.shape[1]:
                i1 = frame.shape[1] - 1
            npix = i1-i0                       # Length of aperture
            col_array = np.zeros((npix,4))     # (aper_size, 3) array, containing,
            col_array[:,0] = np.array(range(i0,i1))-ord_pos[integration, col]    # pix position from center
            col_array[:,1] = frame[integration, i0:i1, col]                      # data at those points, and
            col_array[:,2] = variance[integration, i0:i1, col]                   # variance on those data points
            col_array[:,3] = np.ones(npix)*col
            col_array_pos[integration, col, 1] = npix
            col_pos += npix
            pix_list.append(col_array)         # Is a list containing col_array for each column
        
    # Make continuous array out of list of arrays
    num_entries = np.sum([p.shape[0] for p in pix_list])
    pix_array = np.zeros((num_entries,4))
    entry = 0
    for p in pix_list:
        N = len(p)
        pix_array[entry:(entry+N),:] = p
        entry += N
    return pix_array, col_array_pos

def norm_flux_coo(pix_array, col_array_pos, spec = None):
    """ Normalises the fluxes by summing up pixel values.
    
    Given the pixel array and col_array_pos from `flux_coo`
    function, this function provides the normalized fluxes.
    If no normalisation spectrum is provided, the pixel sum is used.

    Parameters
    ----------
    pix_array : ndarray
        Array with pixel coordinates, flux and variance, as
        returned by `flux_coo`.
    col_array_pos : ndarray
        Array containing column indices in `pix_array`, as
        returned by `flux_coo`.
    spec : ndarray, optional
        2D array, of [nints, ncols] size, providing normalisation spectrum.
    
    Returns
    -------
    norm_array : ndarray
        Array with pixel coordinates, normalized flux, normalized variance
        and column indices.
    """
    norm_array = pix_array.copy()
    ncols = col_array_pos.shape[1]
    nints = col_array_pos.shape[0]
    min_norm = 0.01
    for integration in range(nints):
        for col in range(ncols):
            ind0 = col_array_pos[integration, col, 0]
            ind1 = ind0 + col_array_pos[integration, col, 1]
            if spec is None:
                norm_sum = np.sum(pix_array[ind0:ind1,1])
            else:
                norm_sum = spec[integration, col]
            norm_sum = np.maximum(norm_sum, min_norm)
            norm_array[ind0:ind1,1] = pix_array[ind0:ind1,1]/norm_sum
            norm_array[ind0:ind1,2] = pix_array[ind0:ind1,2]/norm_sum**2
    return norm_array