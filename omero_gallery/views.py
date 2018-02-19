from django.http import Http404

import omero
from omero.rtypes import wrap
from omeroweb.webclient.decorators import login_required, render_response


@login_required()
@render_response()
def index(request, conn=None, **kwargs):
    """
    Home page shows a list of Projects from all of our groups
    """

    my_groups = list(conn.getGroupsMemberOf())

    # Need a custom query to get 1 (random) image per Project
    query_service = conn.getQueryService()
    params = omero.sys.ParametersI()
    params.theFilter = omero.sys.Filter()
    params.theFilter.limit = wrap(1)

    query = "select count(obj.id) from %s as obj"

    groups = []
    for g in my_groups:
        conn.SERVICE_OPTS.setOmeroGroup(g.id)
        images = list(conn.getObjects("Image", params=params))
        if len(images) == 0:
            continue        # Don't display empty groups
        p_count = query_service.projection(
            query % 'Project', None, conn.SERVICE_OPTS)
        d_count = query_service.projection(
            query % 'Dataset', None, conn.SERVICE_OPTS)
        i_count = query_service.projection(
            query % 'Image', None, conn.SERVICE_OPTS)
        groups.append({
            'id': g.getId(),
            'name': g.getName(),
            'description': g.getDescription(),
            'projectCount': p_count[0][0]._val,
            'datasetCount': d_count[0][0]._val,
            'imageCount': i_count[0][0]._val,
            'image': len(images) > 0 and images[0] or None})

    # This is used by @render_response
    context = {'template': "webgallery/index.html"}
    context['groups'] = groups

    return context


@login_required()
@render_response()
def show_group(request, group_id, conn=None, **kwargs):
    conn.SERVICE_OPTS.setOmeroGroup(group_id)

    s = conn.groupSummary(group_id)
    group_owners = s["leaders"]
    group_members = s["colleagues"]
    group = conn.getObject("ExperimenterGroup", group_id)

    # Get NEW user_id, OR current user_id from session OR 'All Members' (-1)
    user_id = request.REQUEST.get(
        'user_id', request.session.get('user_id', -1))
    user_ids = [u.id for u in group_owners]
    user_ids.extend([u.id for u in group_members])
    user_id = int(user_id)
    # Check user is in group
    if user_id not in user_ids and user_id is not -1:
        user_id = -1
    # save it to session
    request.session['user_id'] = int(user_id)
    request.session.modified = True

    query_service = conn.getQueryService()
    params = omero.sys.ParametersI()
    params.theFilter = omero.sys.Filter()
    params.theFilter.limit = wrap(1)
    # params.map = {}
    query = "select i from Image as i"\
            " left outer join i.datasetLinks as dl join dl.parent as dataset"\
            " left outer join dataset.projectLinks"\
            " as pl join pl.parent as project"\
            " where project.id = :pid"
    param_all = omero.sys.ParametersI()
    count_images = "select count(i), count(distinct dataset) from Image as i"\
                   " left outer join i.datasetLinks"\
                   " as dl join dl.parent as dataset"\
                   " left outer join dataset.projectLinks"\
                   " as pl join pl.parent as project"\
                   " where project.id = :pid"

    if user_id == -1:
        user_id = None
    projects = []
    # Will be from active group, owned by user_id (as perms allow)
    for p in conn.listProjects(eid=user_id):
        pdata = {'id': p.getId(), 'name': p.getName()}
        pdata['description'] = p.getDescription()
        pdata['owner'] = p.getDetails().getOwner().getOmeName()
        # Look-up a single image
        params.addLong('pid', p.getId())
        img = query_service.findByQuery(query, params, conn.SERVICE_OPTS)
        if img is None:
            continue    # Ignore projects with no images
        pdata['image'] = {'id': img.getId().getValue(),
                          'name': img.getName().getValue()}
        param_all.addLong('pid', p.getId())
        image_count = query_service.projection(
            count_images, param_all, conn.SERVICE_OPTS)
        pdata['imageCount'] = image_count[0][0].val
        pdata['datasetCount'] = image_count[0][1].val
        projects.append(pdata)

    query = "select i from Image as i"\
            " left outer join i.datasetLinks as dl"\
            " join dl.parent as dataset"\
            " where dataset.id = :did"
    count_images = "select count(i) from Image as i"\
                   " left outer join i.datasetLinks as dl "\
                   "join dl.parent as dataset"\
                   " where dataset.id = :did"
    datasets = []
    for d in conn.listOrphans("Dataset", eid=user_id):
        ddata = {'id': d.getId(), 'name': d.getName()}
        ddata['description'] = d.getDescription()
        ddata['owner'] = d.getDetails().getOwner().getOmeName()
        # Look-up a single image
        # params.map['did'] = wrap(d.id)
        params.addLong('did', d.getId())
        img = query_service.findByQuery(query, params, conn.SERVICE_OPTS)
        if img is None:
            continue    # ignore datasets with no images
        ddata['image'] = {'id': img.getId().getValue(),
                          'name': img.getName().getValue()}
        param_all.addLong('did', d.getId())
        image_count = query_service.projection(
            count_images, param_all, conn.SERVICE_OPTS)
        ddata['imageCount'] = image_count[0][0].val
        datasets.append(ddata)
    context = {'template': "webgallery/show_group.html"}
    context['group'] = group
    context['group_owners'] = group_owners
    context['group_members'] = group_members
    context['projects'] = projects
    context['datasets'] = datasets

    return context


@login_required()
@render_response()
def show_project(request, project_id, conn=None, **kwargs):
    """
    Show a project
    """

    project = conn.getObject("Project", project_id)

    if project is None:
        raise Http404

    # Set a limit to grab 5 images from each Dataset
    params = omero.sys.Parameters()
    params.theFilter = omero.sys.Filter()
    params.theFilter.limit = wrap(5)

    datasets = []
    for ds in project.listChildren():
        # want to display 5 images from each dataset
        images = ds.listChildren(params=params)
        datasets.append({
            "id": ds.getId(),
            "name": ds.getName(),
            "description": ds.getDescription(),
            "images": images})

    context = {'template': "webgallery/show_project.html"}
    context['project'] = project
    context['datasets'] = datasets

    return context


@login_required()
@render_response()
def show_dataset(request, dataset_id, conn=None, **kwargs):
    """
    Show a dataset
    """

    dataset = conn.getObject("Dataset", dataset_id)

    if dataset is None:
        raise Http404

    context = {'template': "webgallery/show_dataset.html"}
    context['dataset'] = dataset

    return context

@login_required()
@render_response()
def show_roi_table(request, image_id, conn=None, **kwargs):
    """
    Show a roi_table
    """

    sc = conn.getObject('Image', image_id)
    for ann in sc.listAnnotations():
        if isinstance(ann, omero.gateway.FileAnnotationWrapper):
            if (ann.getFile().getName() == 'Test_Table'):
                ofId = ann.getFile().getId()
                #Check size of file here and handle pagination(if need be)
                break
    original_file = omero.model.OriginalFileI(ofId, False)
    openTable = conn.c.sf.sharedResources().openTable(original_file)
    rowCount = openTable.getNumberOfRows()
    
    table_column_names = [col.name for col in openTable.getHeaders()]
    print table_column_names
    black_list = []
    column_indices = []
    for column_name in table_column_names:
        if column_name in black_list:
            continue
        column_indices.append(table_column_names.index(column_name))
    
    data = openTable.slice(None, None)

    roi_table_data = {}
    for index in range(rowCount):
        row_values = [column.values[index] for column in data.columns]
        roi_table_data[index] = row_values
        if index==0:
            print row_values

    shapes = []
    roi_service = conn.getRoiService()
    result = roi_service.findByImage(long(image_id), None)
    cntr = 0
    for roi in result.rois:
        # print "ROI:  ID:", roi.getId().getValue()
        for s in roi.copyShapes():
            shape = {}
            shape['roi_id'] = roi.id.val
            shape['id'] = s.getId().getValue()
            theT = -1
            theC = -1
            theZ = -1
            if s.getTheT() is not None:
                theT = s.getTheT().getValue()
            if s.getTheC() is not None:
                theC = s.getTheC().getValue()
            if s.getTheZ() is not None:
                theZ = s.getTheZ().getValue()
            shape['theT'] = theT
            shape['theZ'] = theZ
            shape['theC'] = theC
            shape['data'] = roi_table_data[cntr]
            cntr = cntr + 1
            if s.getTextValue():
                shape['textValue'] = s.getTextValue().getValue()

            shapes.append(shape)

    context = {'template': "webgallery/show_roi_table.html"}
    context['shapes'] = shapes
    context['table_col_names'] = table_column_names

    return context

@login_required()
@render_response()
def show_roi_in_preview(request, roi_id, conn=None, **kwargs):

    shapes = []
    roi_service = conn.getRoiService()
    result = roi_service.findByRoi(long(roi_id), None)
    roi = result.rois[0]
    image = conn.getObject('image', roi.image.id.val)
    if roi is None:
        raise Http404
    points = ''
    for s in roi.copyShapes():
        print(s.getPoints().val)
        points = s.getPoints().val.replace(' ','L')
        points = 'M' + points
        theT = 0
        theC = 0
        theZ = 0
        if s.getTheT() is not None:
            theT = s.getTheT().getValue()
        if s.getTheC() is not None:
            theC = s.getTheC().getValue()
        if s.getTheZ() is not None:
            theZ = s.getTheZ().getValue()
        shape = {}
        shape['theT'] = theT
        shape['theZ'] = theZ
        shape['theC'] = theC

    context = {'template': "webgallery/show_roi_in_preview.html"}
    context['points'] = points
    context['image_id'] = image.id
    context['image_width'] = image.getSizeX()
    context['image_height'] = image.getSizeY()
    context['shape'] = shape

    return context



@login_required()
@render_response()
def show_image(request, image_id, conn=None, **kwargs):
    """
    Show an image
    """

    image = conn.getObject("Image", image_id)

    if image is None:
        raise Http404

    tags = []
    for ann in image.listAnnotations():
        if isinstance(ann, omero.gateway.TagAnnotationWrapper):
            tags.append(ann)

    context = {'template': "webgallery/show_image.html"}
    context['image'] = image
    context['tags'] = tags

    return context
